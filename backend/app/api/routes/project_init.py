"""项目初始化后台任务：异步生成世界观/角色/大纲。

对标 MuMuAINovel 的后台批量生成。用户提交后立即返回任务ID，
后端 asyncio.create_task 执行，前端轮询 /status 查进度。

生成顺序（优化后）：
1. 世界观（核心 + 详细）
2. 职业体系
3. 角色（含主角/配角/反派）
4. 角色关系图谱
5. 组织势力 + 角色组织关联
6. 地点地图
7. 物品道具
8. 大纲（默认3章，用户可选）
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func


# 角色英文 role → 中文映射
ROLE_MAP = {
    "protagonist": "主角", "main": "主角", "主角": "主角",
    "antagonist": "反派", "villain": "反派", "反派": "反派",
    "supporting": "配角", "side": "配角", "配角": "配角",
    "minor": "路人", "passby": "路人", "路人": "路人",
}

# 初始化步骤定义（名称, 进度, done 字段名）
# 顺序优化：世界观 → 职业 → 组织 → 角色 → 职业分配 → 关系 → 组织成员分配 → 大纲
# 组织提前到角色之前，这样角色生成时 AI 可指定所属组织，关联更可靠
# 后置自动分配组织成员，确保所有角色都有组织归属
# 生成顺序：世界观 → 职业 → 角色 → 地点 → 物品 → 组织 → 关系 → 大纲 → 验证
# 理念：地点、物品属于静态设定，角色和冲突才是核心。先有人，再有场景和道具。
INIT_STEPS = [
    ("world", "世界观", 5, "world_done"),
    ("career", "职业体系", 15, "career_done"),
    ("characters", "角色", 35, "characters_done"),
    ("locations", "地点地图", 50, "locations_done"),
    ("items", "物品道具", 60, "items_done"),
    ("org", "组织势力", 75, "org_done"),
    ("relations", "角色关系", 85, "relations_done"),
    ("outline", "大纲", 92, "outline_done"),
    ("validate_outline", "验证补全", 97, "validate_done"),
]
STEP_ORDER = [s[0] for s in INIT_STEPS]


async def _safe_skill_call(engine, ai_client, skill_name, context, label="步骤", max_retries=1, tools=None, tool_executor=None):
    """带重试的 skill 调用。
    
    每次调用内部含 execute_skill 的 JSON 重试（AI_MAX_RETRIES=1 次），
    这里额外重试 max_retries 次，处理连接级错误。
    支持透传 tools 和 tool_executor 给 execute_skill。
    """
    import logging
    logger = logging.getLogger(__name__)
    last_err = None
    for attempt in range(max_retries):
        try:
            result = await engine.execute_skill(skill_name, ai_client, context, tools=tools, tool_executor=tool_executor)
            if not result.get("error"):
                return result, None
            last_err = result.get("error")
            logger.warning(f"[init] {label} 第{attempt+1}次失败: {last_err[:200]}")
        except Exception as e:
            last_err = str(e)
            logger.warning(f"[init] {label} 第{attempt+1}次异常: {last_err[:200]}")
        if attempt < max_retries - 1:
            delay = min(2 * (attempt + 1), 10)
            logger.info(f"[init] {label}第{attempt+1}次重试，等待{delay}秒...")
            await asyncio.sleep(delay)
    logger.error(f"[init] {label} 全部{max_retries}次尝试失败，最后错误: {last_err[:300]}")
    return None, f"{label}失败（已重试{max_retries}次）: {last_err}"


def _build_world_info(proj) -> str:
    """构建完整的世界观上下文字符串（四个维度）。"""
    parts = []
    if proj.world_time_period:
        parts.append(f"时间背景：{proj.world_time_period}")
    if proj.world_location:
        parts.append(f"地理位置：{proj.world_location}")
    if proj.world_atmosphere:
        parts.append(f"氛围基调：{proj.world_atmosphere}")
    if proj.world_rules:
        parts.append(f"世界规则：{proj.world_rules}")
    return "\n".join(parts) if parts else "暂无世界观信息"


from app.core.database import get_db, async_session
from app.core.auth import get_current_user
from app.models.project import Project
from app.models.project_init_task import ProjectInitTask
from app.skills.engine import SkillEngine
from app.core.ai_client import AIClient
from app.services.chapter_tools import get_chapter_tools, make_tool_executor

router = APIRouter(prefix="/api/projects", tags=["项目初始化"])


def _map_role(raw_role: str, default="配角") -> str:
    """将英文 role_type 映射为中文。"""
    if not raw_role:
        return default
    key = str(raw_role).strip().lower()
    return ROLE_MAP.get(key, ROLE_MAP.get(str(raw_role).strip(), default))


def _join_sub_occupations(item: dict) -> str:
    """从 AI 返回中提取副职业列表，拼成分号分隔字符串。"""
    raw = item.get("sub_occupations") or item.get("secondary_occupations") or item.get("sub_careers") or []
    if isinstance(raw, str):
        # 已是字符串，按分号/逗号归一
        parts = [p.strip() for p in raw.replace("，", ";").replace(",", ";").split(";") if p.strip()]
        return ";".join(parts)[:500]
    if isinstance(raw, list):
        parts = []
        for o in raw:
            if isinstance(o, str):
                parts.append(o.strip())
            elif isinstance(o, dict):
                n = o.get("name") or o.get("occupation") or ""
                if n:
                    parts.append(str(n).strip())
        return ";".join(p for p in parts if p)[:500]
    return ""


async def _step_world(db, task, pid, proj, engine, ai_client):
    """步骤1：核心世界观 + 详细设定"""
    from app.models.world import WorldSetting

    task.status_message = "生成核心世界观..."
    task.progress = 5
    await db.commit()

    result, werr = await _safe_skill_call(engine, ai_client, "world_core_generate", {
        "genre": proj.genre or "网文", "title": proj.title, "synopsis": proj.synopsis or "暂无",
        "user_prompt": f"请为《{proj.title}》生成核心世界观。",
    }, "世界观")
    if werr:
        return werr
    data = result.get("json") or {}
    if isinstance(data, dict):
        proj.world_time_period = str(data.get("world_time_period", ""))[:2000]
        proj.world_location = str(data.get("world_location", ""))[:2000]
        proj.world_atmosphere = str(data.get("world_atmosphere", ""))[:2000]
        proj.world_rules = str(data.get("world_rules", ""))[:2000]
        await db.commit()

    task.progress = 10
    await db.commit()

    # 详细世界设定
    detail_result, derr = await _safe_skill_call(engine, ai_client, "world_detail_generate", {
        "genre": proj.genre or "网文", "title": proj.title,
        "synopsis": proj.synopsis or "暂无",
        "world_info": _build_world_info(proj),
        "user_prompt": "请生成 6-8 个详细世界设定条目。",
    }, "详细设定", max_retries=2)
    if not derr and detail_result:
        items = detail_result.get("json") or []
        if isinstance(items, list):
            for item in items[:10]:
                if isinstance(item, dict) and item.get("name"):
                    db.add(WorldSetting(project_id=pid,
                        name=str(item.get("name", ""))[:100],
                        category=str(item.get("category", "其他"))[:50],
                        content=str(item.get("content", ""))[:2000]))
            await db.commit()

    task.world_done = 1
    return None


async def _step_career(db, task, pid, proj, engine, ai_client):
    """步骤2：职业体系（拆分为两次请求：先主职业，后副职业，避免 Cloudflare 超时）"""
    from app.models.career import Career

    task.status_message = "生成职业体系..."
    await db.commit()

    world_info = _build_world_info(proj)
    all_careers = []

    # 第一次：生成主职业（5 个，带完整境界体系）
    task.status_message = "生成主职业..."
    await db.commit()
    main_result, cerr = await _safe_skill_call(engine, ai_client, "career_system_generation", {
        "title": proj.title, "genre": proj.genre or "网文",
        "world_info": world_info,
        "user_prompt": (
            f"请为《{proj.title}》设计 5 个主职业（career_type=\"main\"）。"
            f"每个主职业需有完整的进阶境界体系（stages 数组，5-9 个阶段，每阶段含 name/level/requirement/ability/power_level）。"
            f"主职业是世界观的核心力量体系，请设计得详细且有特色。"
        ),
    }, "主职业")
    if cerr:
        return cerr
    main_data = main_result.get("json")
    if isinstance(main_data, list):
        all_careers.extend(main_data)
    elif isinstance(main_data, dict):
        for key in ("main_careers", "careers"):
            items = main_data.get(key, [])
            if isinstance(items, list):
                all_careers.extend(items)
        if not all_careers and main_data.get("name"):
            all_careers.append(main_data)

    # 第二次：生成副职业（8 个，进阶阶段精简）
    task.status_message = "生成副职业..."
    await db.commit()
    sub_result, cerr = await _safe_skill_call(engine, ai_client, "career_system_generation", {
        "title": proj.title, "genre": proj.genre or "网文",
        "world_info": world_info,
        "user_prompt": (
            f"请为《{proj.title}》设计 8 个副职业（career_type=\"sub\"）。"
            f"副职业是主职业的补充和变体，有 3-5 个精简的进阶阶段。"
            f"可以和已生成的主职业有关联，但不要重复。直接输出副职业的 JSON 数组。"
        ),
    }, "副职业")
    if cerr:
        return cerr
    sub_data = sub_result.get("json")
    if isinstance(sub_data, list):
        all_careers.extend(sub_data)
    elif isinstance(sub_data, dict):
        for key in ("sub_careers", "careers"):
            items = sub_data.get(key, [])
            if isinstance(items, list):
                all_careers.extend(items)
        if not all_careers and sub_data.get("name"):
            all_careers.append(sub_data)

    for item in all_careers[:15]:
        if isinstance(item, dict) and item.get("name"):
            db.add(Career(project_id=pid,
                name=str(item.get("name", ""))[:100],
                career_type=str(item.get("career_type", item.get("type", "main")))[:20],
                category=str(item.get("category", ""))[:50],
                description=str(item.get("description", ""))[:2000],
                stages=item.get("stages", item.get("requirements", [])),
                abilities=item.get("abilities", item.get("special_abilities", item.get("abilities_list", []))),
            ))
    await db.commit()
    task.career_done = 1
    return None


async def _step_characters(db, task, pid, proj, engine, ai_client):
    """步骤：角色批量生成（含主角/配角/反派，职业从已有体系中选择）。

    组织在后续步骤生成，角色暂不关联组织。
    """
    import logging
    logger = logging.getLogger(__name__)
    from app.models.character import Character

    existing_count = (await db.execute(
        select(func.count(Character.id)).where(Character.project_id == pid)
    )).scalar() or 0
    if existing_count >= 3:
        logger.info(f"[init] 已有{existing_count}个角色，跳过生成")
        task.characters_done = 1
        task.status_message = f"已有 {existing_count} 个角色"
        await db.commit()
        return None

    task.status_message = "生成角色..."
    await db.commit()

    from app.models.career import Career
    careers = (await db.execute(select(Career).where(Career.project_id == pid))).scalars().all()
    career_info = "、".join(f"{c.name}({c.career_type})" for c in careers[:8]) if careers else "暂无"

    result, cerr = await _safe_skill_call(engine, ai_client, "characters_batch_generation", {
        "genre": proj.genre or "网文", "title": proj.title,
        "synopsis": proj.synopsis or "暂无简介", "count": "5",
        "existing_characters": "暂无",
        "world_info": _build_world_info(proj),
        "user_prompt": (
            f"请生成5个角色（必须包含1个主角、1个反派、其余配角）。\n"
            f"已有职业体系：{career_info}\n"
            f"组织将在后续步骤生成，角色的 organization_memberships 暂返回空数组 []。"
        ),
    }, "角色")
    if cerr:
        return cerr

    chars_data = result.get("json") or []
    if not isinstance(chars_data, list):
        logger.error(f"[init] 角色生成返回非数组格式: {type(chars_data)}")
        return "角色生成返回格式错误"

    existing_names = set()
    await _save_characters(db, pid, chars_data, existing_names)

    if existing_names:
        task.characters_done = 1
        task.status_message = f"已生成 {len(existing_names)} 个角色"
    else:
        logger.error(f"[init] 角色生成失败：AI返回了{len(chars_data)}条数据但没有有效角色")
        return "角色生成失败：没有有效角色"
    await db.commit()
    logger.info(f"[init] 角色生成完成，共{len(existing_names)}个")
    return None


async def _save_characters(db, pid, chars_data, existing_names: set):
    """保存角色到数据库，含职业体系匹配。"""
    import logging
    logger = logging.getLogger(__name__)
    from app.models.character import Character
    from app.models.career import Career

    all_careers = (await db.execute(select(Career).where(Career.project_id == pid))).scalars().all()
    main_career_map = {c.name: c.id for c in all_careers if c.career_type == 'main'}
    sub_career_map = {c.name: c.id for c in all_careers if c.career_type == 'sub'}
    all_career_map = {c.name: c.id for c in all_careers}
    career_by_id = {c.id: c for c in all_careers}

    def _default_stage(career_obj):
        stages = career_obj.stages or []
        return stages[0].get("name", "") if stages else ""

    for item in chars_data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        char_name = str(item.get("name", "")).strip()
        if item.get("is_organization") or item.get("is_org"):
            continue
        if char_name in existing_names:
            continue
        existing_names.add(char_name)

        raw_role = item.get("role", item.get("role_type", item.get("character_role", "")))
        mapped_role = _map_role(raw_role)

        traits = item.get("traits", item.get("abilities_list", []))
        ability_text = "、".join(str(t) for t in traits if t) if isinstance(traits, list) else ""

        char = Character(
            project_id=pid,
            name=char_name[:100],
            role=mapped_role[:100],
            gender=str(item.get("gender", ""))[:50],
            age=str(item.get("age", ""))[:50],
            appearance=str(item.get("appearance", item.get("look", "")))[:2000],
            personality=str(item.get("personality", item.get("character_traits", "")))[:2000],
            background=str(item.get("background", item.get("history", "")))[:2000],
            growth_experience=str(item.get("growth_experience", item.get("growth", item.get("backstory", item.get("origin", "")))))[:2000],
            ability=str(item.get("ability", item.get("abilities", item.get("skills", ability_text))))[:2000],
            story_goal=str(item.get("story_goal", item.get("goal", item.get("core_goal", ""))))[:2000],
            motivation=str(item.get("motivation", item.get("internal_motivation", item.get("driving_force", item.get("inner_drive", "")))))[:2000],
            weakness=str(item.get("weakness", item.get("pressure_point", item.get("vulnerability", ""))))[:2000],
            identity=str(item.get("identity", item.get("social_role", item.get("identity_role", ""))))[:200],
            occupation=str(item.get("occupation", item.get("profession", item.get("main_career", ""))))[:200],
            sub_occupations=_join_sub_occupations(item)[:500],
            speech_style=str(item.get("speech_style", item.get("dialogue_style", item.get("speech_pattern", ""))))[:200],
            arc_type=str(item.get("arc_type", item.get("character_arc", "")))[:200],
            character_change=str(item.get("character_change", item.get("transformation", "")))[:2000],
        )
        db.add(char)

        # 主职业匹配（在 flush 前先存到 char 上，flush 后再设 id 会失败）
        occ_raw = str(item.get("occupation", ""))
        occ_parts = [p.strip() for p in occ_raw.replace("/", ",").replace("、", ",").split(",") if p.strip()]
        for occ in occ_parts:
            if occ in main_career_map:
                char.main_career_id = main_career_map[occ]
                ai_stage = str(item.get("main_career_stage", "")).strip()
                char.main_career_stage_desc = ai_stage if ai_stage else _default_stage(career_by_id.get(char.main_career_id))
                break
            for cname, cid in main_career_map.items():
                if occ in cname or cname in occ:
                    char.main_career_id = cid
                    ai_stage = str(item.get("main_career_stage", "")).strip()
                    char.main_career_stage_desc = ai_stage if ai_stage else _default_stage(career_by_id.get(cid))
                    break

        # 副职业匹配
        sub_names = set()
        subs_raw = item.get("sub_occupations") or []
        if isinstance(subs_raw, str):
            subs_raw = [s.strip() for s in subs_raw.replace("，", ",").replace("/", ",").split(",") if s.strip()]
        for sn in subs_raw:
            sub_names.add(str(sn).strip())
        for occ in occ_parts:
            if not char.main_career_id or all_career_map.get(occ) != char.main_career_id:
                sub_names.add(occ)

        ai_sub_stages = item.get("sub_career_stages") or []
        if isinstance(ai_sub_stages, str):
            ai_sub_stages = [s.strip() for s in ai_sub_stages.split(",") if s.strip()]

        sub_list = []
        for sn in sub_names:
            cid = None
            cname = sn
            if sn in sub_career_map:
                cid = sub_career_map[sn]
            elif sn in all_career_map:
                cid = all_career_map[sn]
            else:
                for cn, ci in all_career_map.items():
                    if sn in cn or cn in sn:
                        cid = ci
                        cname = cn
                        break
            if cid and cid != char.main_career_id:
                stage = ""
                sn_list = list(sub_names)
                idx = sn_list.index(sn) if sn in sn_list else -1
                if 0 <= idx < len(ai_sub_stages):
                    stage = str(ai_sub_stages[idx]).strip()
                if not stage:
                    stage = _default_stage(career_by_id.get(cid))
                sub_list.append({"career_id": cid, "name": cname, "stage_desc": stage})
        char.sub_careers = sub_list


async def _link_org_memberships(db, pid, raw_chars):
    """从 AI 返回的数据中提取组织关联，写入 Character.organization_id + OrganizationMember。

    修复：去掉 break，一个角色所属的所有组织都写入 OrganizationMember；
    organization_id 记录主组织（第一个匹配的）。
    """
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from sqlalchemy import func

    orgs = (await db.execute(select(Organization).where(Organization.project_id == pid))).scalars().all()
    if not orgs:
        return
    org_name_to_id = {o.name: o.id for o in orgs}

    for char, item in raw_chars:
        memberships = item.get("organization_memberships", item.get("organizations", []))
        if not memberships:
            continue
        if isinstance(memberships, str):
            memberships = [memberships]
        first_linked = False  # organization_id 只记第一个匹配
        for org_name in memberships:
            if isinstance(org_name, dict):
                org_name = org_name.get("name", org_name.get("organization", ""))
            org_name = str(org_name).strip()
            # 模糊匹配组织名
            org_id = org_name_to_id.get(org_name)
            if not org_id:
                for o_name, o_id in org_name_to_id.items():
                    if org_name in o_name or o_name in org_name:
                        org_id = o_id
                        break
            if org_id:
                # organization_id 记主组织（第一个匹配），其余仍写入多对多表
                if not first_linked:
                    char.organization_id = org_id
                    first_linked = True
                # 所有匹配的组织都写入 OrganizationMember（避免重复）
                existing = await db.scalar(
                    select(func.count(OrganizationMember.id)).where(
                        OrganizationMember.organization_id == org_id,
                        OrganizationMember.character_id == char.id,
                    )
                )
                if not existing:
                    db.add(OrganizationMember(
                        organization_id=org_id,
                        character_id=char.id,
                        position=item.get("org_role", "成员")[:50] if isinstance(item.get("org_role"), str) else "成员",
                        status="active",
                    ))


async def _step_assign_careers(db, task, pid, proj, engine, ai_client):
    """步骤：为角色自动分配主职业（初始化时自动执行）。

    改进：传递完整的角色/职业/世界观上下文，让 AI 有足够信息做出精准匹配。
    """
    from app.models.character import Character
    from app.models.career import Career
    from app.models.character_career import CharacterCareer

    task.status_message = "分配角色职业..."
    await db.commit()

    careers = (await db.execute(select(Career).where(Career.project_id == pid))).scalars().all()
    if not careers:
        task.assign_careers_done = 1
        return None

    # 构建详细职业列表（含描述、境界、能力）
    career_parts = []
    for c in careers:
        stage_names = []
        if c.stages and isinstance(c.stages, list):
            stage_names = [s.get("name", "") for s in c.stages[:5] if isinstance(s, dict)]
        stage_preview = " → ".join(stage_names) if stage_names else "无境界数据"
        abilities = "、".join(c.abilities[:3]) if isinstance(c.abilities, list) and c.abilities else "无"
        career_parts.append(
            f"- ID:{c.id} {c.name}（{c.career_type or 'main'}，{c.category or '通用'}）\n"
            f"  描述：{(c.description or '')[:200]}\n"
            f"  境界：{stage_preview}\n"
            f"  核心能力：{abilities}"
        )
    career_list = "\n".join(career_parts)

    # 已有主职业的角色 ID（已通过 _step_characters 的 occupation 匹配过的）
    assigned_ids = [cc.character_id for cc in (await db.execute(
        select(CharacterCareer).where(CharacterCareer.project_id == pid, CharacterCareer.career_type == "main")
    )).scalars().all()]

    chars = (await db.execute(
        select(Character).where(
            Character.project_id == pid,
            ~Character.id.in_(assigned_ids) if assigned_ids else True,
        ).limit(20)
    )).scalars().all()

    if not chars:
        task.assign_careers_done = 1
        return None

    # 构建详细角色列表（含身份/背景/目标/动机/能力）
    char_parts = []
    for c in chars:
        info = [f"- ID:{c.id} {c.name}（{c.role or '角色'}，{c.gender}，{c.age or '?'}岁）"]
        if c.identity:
            info.append(f"  身份：{c.identity[:100]}")
        if c.occupation:
            info.append(f"  当前职业标注：{c.occupation[:80]}")
        if c.personality:
            info.append(f"  性格：{c.personality[:150]}")
        if c.background:
            info.append(f"  背景：{c.background[:150]}")
        if c.ability:
            info.append(f"  能力：{c.ability[:150]}")
        if c.story_goal:
            info.append(f"  目标：{c.story_goal[:100]}")
        if c.motivation:
            info.append(f"  动机：{c.motivation[:100]}")
        if c.growth_experience:
            info.append(f"  成长经历：{c.growth_experience[:120]}")
        char_parts.append("\n".join(info))
    char_list = "\n\n".join(char_parts)

    world_info = _build_world_info(proj)

    system_prompt = f"""你是资深网文角色设计顾问。为小说《{proj.title}》（题材：{proj.genre or '网文'}）中的角色匹配最合适的主职业。

【小说简介】
{proj.synopsis or '暂无'}

【世界观】
{world_info}

【匹配原则】
1. 职业要与角色的性格、背景、成长经历、能力方向相匹配
2. 主角职业应有成长空间和叙事潜力（不要选过于边缘的职业）
3. 反派的职业应与其野心或对主角的压制关系吻合
4. 配角的职业可以偏向辅助/功能性，但应符合其人设
5. 境界起点要合理：主角略高（但不能满级），反派与主角相当或略高，配角按剧情位置分配

返回纯JSON数组：[{{"character_id":0,"career_id":0,"current_stage":1,"started_at":"开始时间描述"}}]"""

    user_prompt = f"""请为以下角色匹配最合适的职业：

【可用职业体系】
{career_list}

【待分配角色】
{char_list}"""

    result = await ai_client.chat_json_retry(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    if result.get("error"):
        task.assign_careers_done = 1
        return None

    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("assignments") or data.get("data") or []

    char_id_set = {c.id for c in chars}
    career_id_set = {c.id for c in careers}
    created = 0
    for a in data:
        if not isinstance(a, dict):
            continue
        if a.get("character_id") not in char_id_set or a.get("career_id") not in career_id_set:
            continue
        try:
            db.add(CharacterCareer(
                project_id=pid,
                character_id=int(a["character_id"]),
                career_id=int(a["career_id"]),
                career_type="main",
                current_stage=max(1, int(a.get("current_stage", 1))),
                started_at=str(a.get("started_at", ""))[:100],
                source="ai",
            ))
            created += 1
        except Exception:
            continue

    await db.commit()
    task.assign_careers_done = 1
    task.status_message = f"已为 {created} 个角色分配职业"
    return None


def _extract_rel_endpoint(rel, is_from):
    """从 AI 返回的关系对象中提取端点（角色名或ID）。

    AI 返回字段名多变，兼容 from/from_character/character_a/source/name_a 等，
    以及 from_id/to_id 数字ID。返回 (id_or_None, name_or_None)。
    """
    id_keys = ["from_id", "to_id"] if is_from else ["to_id", "from_id"]
    name_keys = (["from", "from_character", "character_a", "source", "name_a", "char_a", "a"]
                 if is_from else
                 ["to", "to_character", "character_b", "target", "name_b", "char_b", "b"])
    # 优先数字ID
    for k in id_keys:
        v = rel.get(k)
        if isinstance(v, int) or (isinstance(v, str) and v.strip().isdigit()):
            return int(v), None
    # 再取名字
    for k in name_keys:
        v = rel.get(k)
        if isinstance(v, str) and v.strip():
            return None, v.strip()
        if isinstance(v, dict):  # 嵌套 {name:...}
            inner = v.get("name") or v.get("character") or v.get("id")
            if inner:
                return (None, str(inner).strip()) if not (isinstance(inner, int) or str(inner).strip().isdigit()) else (int(inner), None)
    return None, None


def _match_character(name, id_val, chars, name_to_id):
    """精确匹配 → 模糊匹配（包含），返回 character_id 或 None。"""
    # 1) 数字ID直配
    if id_val is not None:
        for c in chars:
            if c.id == id_val:
                return c.id
    if not name:
        return None
    # 2) 精确匹配
    if name in name_to_id:
        return name_to_id[name]
    # 3) 去除常见后缀/空格后再精确匹配
    clean = name.replace("（主角）", "").replace("(主角)", "").strip()
    if clean in name_to_id:
        return name_to_id[clean]
    # 4) 模糊匹配（互相包含）—— 优先长名（避免"明"匹配"天明"这类误配，要求至少2字）
    if len(clean) >= 2:
        candidates = [c for c in chars if clean in c.name or c.name in clean]
        if len(candidates) == 1:
            return candidates[0].id
    return None


async def _step_relations(db, task, pid, proj, engine, ai_client):
    """步骤：角色关系图谱

    修复历史 bug：旧逻辑用 rel.get("from")/rel.get("to") 精确匹配，
    AI 返回字段变体或名称不精确时静默丢失，导致任务显示成功但图谱为空。
    现在对齐 relations.py:auto_rebuild_relations 的健壮字段处理。
    """
    import logging
    logger = logging.getLogger(__name__)
    from app.models.character import Character, CharacterRelation

    task.status_message = "生成角色关系..."
    await db.commit()

    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    if len(chars) < 2:
        task.relations_done = 1
        return None

    name_to_id = {c.name: c.id for c in chars}
    id_set = {c.id for c in chars}

    # 构建详细角色信息（让 AI 基于性格/背景/目标生成有深度的关系）
    char_parts = []
    for c in chars[:12]:
        info = [f"{c.name}（ID:{c.id}，{c.role or '角色'}，{c.gender or ''}，{c.age or '?'}岁）"]
        if c.identity:
            info.append(f"  身份：{c.identity[:100]}")
        if c.personality:
            info.append(f"  性格：{c.personality[:120]}")
        if c.background:
            info.append(f"  背景：{c.background[:120]}")
        if c.story_goal:
            info.append(f"  目标：{c.story_goal[:80]}")
        if c.motivation:
            info.append(f"  动机：{c.motivation[:80]}")
        if c.weakness:
            info.append(f"  弱点：{c.weakness[:60]}")
        if c.occupation:
            info.append(f"  职业：{c.occupation[:60]}")
        info.append("")
        char_parts.append("\n".join(info))
    char_list = "\n".join(char_parts)

    rel_result, rerr = await _safe_skill_call(engine, ai_client, "character_relations_generate", {
        "title": proj.title,
        "characters_info": char_list,
        "user_prompt": f"请分析《{proj.title}》角色关系，用 from_id/to_id 指明两端，返回纯 JSON 数组。",
    }, "关系图谱")
    if rerr:
        return rerr

    raw = rel_result.get("json")
    # 兼容裸数组 / {"relations": [...]} 两种结构
    rels = []
    if isinstance(raw, list):
        rels = raw
    elif isinstance(raw, dict):
        rels = raw.get("relations", []) or raw.get("data", [])
        if not rels and (raw.get("from_id") or raw.get("from")):
            rels = [raw]

    added_rels = 0
    skipped = 0
    seen = set()  # 去重
    if isinstance(rels, list):
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            from_id_raw, from_name = _extract_rel_endpoint(rel, is_from=True)
            to_id_raw, to_name = _extract_rel_endpoint(rel, is_from=False)
            fid = _match_character(from_name, from_id_raw, chars, name_to_id)
            tid = _match_character(to_name, to_id_raw, chars, name_to_id)
            if not fid or not tid or fid == tid:
                skipped += 1
                continue
            rtype = str(rel.get("relation_type", "关系"))[:100]
            key = (fid, tid, rtype)
            if key in seen:
                continue
            seen.add(key)
            db.add(CharacterRelation(
                project_id=pid,
                from_character_id=fid,
                to_character_id=tid,
                relation_type=rtype,
                category=str(rel.get("category", "social"))[:50],
                intimacy=int(rel.get("intimacy", 50)) if str(rel.get("intimacy", "50")).lstrip("-").isdigit() else 50,
                description=str(rel.get("description", ""))[:500],
            ))
            added_rels += 1
        if added_rels:
            await db.commit()

    # 不再静默成功：0 条关系要明确告知
    if added_rels == 0:
        logger.warning(f"[init] 项目{pid} 角色关系生成0条（AI返回{len(rels)}条，{skipped}条无法匹配）")
        task.status_message = f"角色关系：AI返回{len(rels)}条但均无法匹配到角色，请到「关系图谱」页手动重建"
    else:
        task.status_message = f"已生成 {added_rels} 条角色关系"
        task.relations_done = 1
        return None


async def _step_assign_org_members(db, task, pid, proj, engine, ai_client):
    """步骤：后置自动分配角色到组织（初始化阶段确保所有角色有组织归属）。

    在角色和组织都生成完成后，通过 AI 调用将每个角色分配到最匹配的组织中，
    补全 _link_org_memberships 中因 AI 未返回 organization_memberships 导致
    成员数为 0 的问题。
    """
    import logging
    logger = logging.getLogger(__name__)
    from app.models.character import Character
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from sqlalchemy import func

    task.status_message = "分配角色到组织..."
    await db.commit()

    # 检查是否已有成员关联（可能 _link_org_memberships 已部分成功）
    existing_members = (await db.execute(
        select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id.in_(
                select(Organization.id).where(Organization.project_id == pid)
            )
        )
    )).scalar() or 0

    chars = (await db.execute(
        select(Character).where(Character.project_id == pid)
    )).scalars().all()
    orgs = (await db.execute(
        select(Organization).where(Organization.project_id == pid)
    )).scalars().all()

    if not chars or not orgs:
        task.assign_org_members_done = 1
        task.status_message = "无需分配（缺少角色或组织）"
        await db.commit()
        return None

    # 找出尚未有任何组织归属的角色
    chars_with_org = set()
    for c in chars:
        if c.organization_id:
            chars_with_org.add(c.id)
    # 也查 OrganizationMember 表
    member_rows = (await db.execute(
        select(OrganizationMember.character_id).where(
            OrganizationMember.organization_id.in_([o.id for o in orgs])
        )
    )).scalars().all()
    chars_with_org.update(member_rows)

    unassigned = [c for c in chars if c.id not in chars_with_org]
    if not unassigned:
        logger.info(f"[init] 所有{len(chars)}个角色已有组织归属，跳过分配")
        task.assign_org_members_done = 1
        task.status_message = f"所有角色已有组织归属"
        await db.commit()
        return None

    # 用 AI 为未分配角色匹配合适组织
    org_list = "\n".join(
        f"- ID:{o.id} {o.name}（{o.org_type or '势力'}，势力值:{o.power_value or 50}）\n"
        f"  描述：{(o.description or '')[:200]}\n"
        f"  所在地：{o.location or '未知'}｜格言：{o.motto or '无'}"
        for o in orgs[:10]
    )
    char_parts = []
    for c in unassigned[:20]:
        info = [f"- ID:{c.id} {c.name}（{c.role or '角色'}，{c.gender}，{c.age or '?'}岁）"]
        if c.identity:
            info.append(f"  身份：{c.identity[:100]}")
        if c.occupation:
            info.append(f"  职业：{c.occupation[:80]}")
        if c.personality:
            info.append(f"  性格：{c.personality[:150]}")
        if c.background:
            info.append(f"  背景：{c.background[:150]}")
        if c.story_goal:
            info.append(f"  目标：{c.story_goal[:100]}")
        char_parts.append("\n".join(info))
    char_list = "\n\n".join(char_parts)

    world_info = _build_world_info(proj)

    system_prompt = f"""你是网文势力策划师。为小说《{proj.title}》（题材：{proj.genre or '网文'}）中的角色分配到最合适的组织。

【世界观】
{world_info}

【分配原则】
1. 根据角色性格、背景、职业、目标匹配组织类型和定位
2. 主角通常应有明确的组织归属（正派或中立组织），反派可归属敌对组织
3. 组织的格言/宗旨应与角色的价值观有共鸣或冲突空间
4. 无所属组织的角色（如自由人/独行侠/过客），organization_id 设为 null

返回纯JSON数组：[{{"character_id":0,"organization_id":0,"role":"核心成员"}}]"""

    user_prompt = f"""请将以下角色分配到最合适的组织中：

【可用组织】
{org_list}

【待分配角色】
{char_list}"""

    result = await ai_client.chat_json_retry(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    if result.get("error"):
        logger.warning(f"[init] 组织成员分配 AI 调用失败: {result['error']}")
        task.assign_org_members_done = 1
        task.status_message = f"组织成员分配跳过（AI 调用失败）"
        await db.commit()
        return None

    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("assignments") or data.get("data") or []

    char_id_set = {c.id for c in unassigned}
    org_id_set = {o.id for o in orgs}
    assigned = 0
    for a in data:
        if not isinstance(a, dict):
            continue
        cid = a.get("character_id")
        oid = a.get("organization_id")
        if cid not in char_id_set:
            continue
        if oid and oid not in org_id_set:
            continue
        role = str(a.get("role", "成员"))[:50]
        try:
            # 更新 Character.organization_id（主组织，取第一个匹配）
            char = next((c for c in chars if c.id == cid), None)
            if char and oid:
                if not char.organization_id:
                    char.organization_id = oid
                # 写入 OrganizationMember（所有匹配）
                existing = await db.scalar(
                    select(func.count(OrganizationMember.id)).where(
                        OrganizationMember.organization_id == oid,
                        OrganizationMember.character_id == cid,
                    )
                )
                if not existing:
                    db.add(OrganizationMember(
                        organization_id=oid,
                        character_id=cid,
                        position=role,
                        status="active",
                        source="ai",
                    ))
                    assigned += 1
        except Exception as e:
            logger.warning(f"[init] 分配角色 {cid} 到组织 {oid} 失败: {e}")
            continue

    await db.commit()
    task.assign_org_members_done = 1
    task.status_message = f"已为 {assigned} 个角色分配组织" if assigned else "组织成员分配完成"
    logger.info(f"[init] 组织成员分配完成：{assigned}/{len(unassigned)} 个角色已分配")
    return None


async def _step_org(db, task, pid, proj, engine, ai_client):
    """步骤5：组织势力生成"""
    from app.models.organization import Organization

    task.status_message = "生成组织势力..."
    await db.commit()

    org_result, oerr = await _safe_skill_call(engine, ai_client, "organization_generate", {
        "title": proj.title, "genre": proj.genre or "网文",
        "synopsis": proj.synopsis or "暂无简介",
        "world_info": _build_world_info(proj),
        "user_prompt": f"请为《{proj.title}》生成3-5个组织势力。",
    }, "组织")
    if oerr:
        return oerr

    orgs_data = org_result.get("json") or []
    if not isinstance(orgs_data, list):
        orgs_data = [orgs_data] if isinstance(orgs_data, dict) else []

    for item in orgs_data[:6]:
        if isinstance(item, dict) and item.get("name"):
            pv = item.get("power_value", item.get("power_level", 50))
            try:
                pv = int(pv)
            except Exception:
                pv = 50
            # 富字段存入 structure（prompt 新增 personality/background/purpose/traits 等）
            extra_fields = {}
            for k in ("personality", "background_story", "purpose", "traits"):
                v = item.get(k, "")
                if v:
                    extra_fields[k] = v
            db.add(Organization(project_id=pid,
                name=str(item.get("name", ""))[:100],
                org_type=str(item.get("org_type", item.get("organization_type", item.get("type", ""))))[:50],
                description=str(item.get("description", item.get("background", "")))[:2000],
                power_value=pv,
                location=str(item.get("location", ""))[:200],
                motto=str(item.get("motto", ""))[:200],
                color=str(item.get("color", ""))[:20],
                members=item.get("members", []) if isinstance(item.get("members"), list) else [],
                relations=item.get("relationships", []) if isinstance(item.get("relationships"), list) else [],
                structure=extra_fields if extra_fields else None,
            ))
    await db.commit()

    # ===== 角色-组织关联 =====
    # 组织已生成，现在将角色分配到组织中
    await _link_characters_to_orgs(db, pid, proj, engine, ai_client)

    task.org_done = 1
    return None


async def _link_characters_to_orgs(db, pid, proj, engine, ai_client):
    """将已有角色自动分配到已有组织中（AI 辅助匹配）。"""
    import logging
    logger = logging.getLogger(__name__)
    from app.models.character import Character
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from sqlalchemy import func

    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    orgs = (await db.execute(select(Organization).where(Organization.project_id == pid))).scalars().all()

    if not chars or not orgs:
        return

    # 找未分配组织的角色
    chars_with_org = set()
    for c in chars:
        if c.organization_id:
            chars_with_org.add(c.id)
    member_rows = (await db.execute(
        select(OrganizationMember.character_id).where(
            OrganizationMember.organization_id.in_([o.id for o in orgs])
        )
    )).scalars().all()
    chars_with_org.update(member_rows)
    unassigned = [c for c in chars if c.id not in chars_with_org]
    if not unassigned:
        return

    # 构建 AI prompt
    org_list = "\n".join(
        f"- ID:{o.id} {o.name}（{o.org_type or '势力'}，势力值:{o.power_value or 50}）\n"
        f"  描述：{(o.description or '')[:150]}\n  格言：{o.motto or '无'}"
        for o in orgs[:10]
    )
    char_parts = []
    for c in unassigned[:20]:
        info = [f"- ID:{c.id} {c.name}（{c.role or '角色'}，{c.gender}，{c.age or '?'}岁）"]
        if c.identity: info.append(f"  身份：{c.identity[:100]}")
        if c.occupation: info.append(f"  职业：{c.occupation[:80]}")
        if c.personality: info.append(f"  性格：{c.personality[:120]}")
        if c.background: info.append(f"  背景：{c.background[:120]}")
        if c.story_goal: info.append(f"  目标：{c.story_goal[:80]}")
        char_parts.append("\n".join(info))
    char_list = "\n\n".join(char_parts)

    result = await engine.execute_skill("org_member_assign", ai_client, {
        "title": proj.title,
        "genre": proj.genre or "网文",
        "world_info": _build_world_info(proj),
        "user_prompt": f"""已有组织：
{org_list}

待分配角色：
{char_list}""",
    })
    if result.get("error"):
        logger.warning(f"[init] 组织成员分配失败: {result['error']}")
        return

    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("assignments") or data.get("data") or []

    char_ids = {c.id for c in unassigned}
    org_ids = {o.id for o in orgs}
    assigned = 0
    for a in data:
        if not isinstance(a, dict): continue
        cid = a.get("character_id")
        oid = a.get("organization_id")
        if cid not in char_ids or (oid and oid not in org_ids): continue
        role = str(a.get("role", "成员"))[:50]
        char = next((c for c in chars if c.id == cid), None)
        if char and oid:
            if not char.organization_id:
                char.organization_id = oid
            existing = await db.scalar(
                select(func.count(OrganizationMember.id)).where(
                    OrganizationMember.organization_id == oid,
                    OrganizationMember.character_id == cid,
                )
            )
            if not existing:
                db.add(OrganizationMember(organization_id=oid, character_id=cid, position=role, status="active", source="ai"))
                assigned += 1
    await db.commit()
    logger.info(f"[init] 角色-组织关联完成：{assigned}/{len(unassigned)} 个角色已分配")


async def _step_locations(db, task, pid, proj, engine, ai_client):
    """步骤：地点地图生成"""
    from app.models.location import Location

    task.status_message = "生成地点地图..."
    await db.commit()

    # 获取已有角色信息（地点生成在角色之后，可参考角色设定）
    from app.models.character import Character
    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    char_hint = "、".join(f"{c.name}({c.role})" for c in chars[:8]) if chars else "暂无"

    loc_result, lerr = await _safe_skill_call(engine, ai_client, "locations_generate", {
        "title": proj.title,
        "world_info": _build_world_info(proj),
        "user_prompt": f"请为《{proj.title}》生成5-8个地点，至少1个重要地点。已有角色：{char_hint}。地点应与角色的身份、活动范围、剧情走向相匹配。",
    }, "地点")
    if lerr:
        return lerr

    locs = loc_result.get("json") or []
    if isinstance(locs, list):
        for loc in locs[:10]:
            if isinstance(loc, dict) and loc.get("name"):
                db.add(Location(
                    project_id=pid,
                    name=str(loc.get("name", ""))[:100],
                    location_type=str(loc.get("location_type", "城市"))[:50],
                    description=str(loc.get("description", ""))[:2000],
                    atmosphere=str(loc.get("atmosphere", ""))[:500],
                    importance=str(loc.get("importance", "normal"))[:20],
                    source="ai",
                ))
        await db.commit()
    task.locations_done = 1
    return None


async def _step_items(db, task, pid, proj, engine, ai_client):
    """步骤：物品道具生成"""
    from app.models.item import Item

    task.status_message = "生成物品道具..."
    await db.commit()

    # 获取已有角色和地点信息（物品生成在它们之后，可参考）
    from app.models.character import Character
    from app.models.location import Location
    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    locs = (await db.execute(select(Location).where(Location.project_id == pid))).scalars().all()
    char_hint = "、".join(f"{c.name}({c.role})" for c in chars[:8]) if chars else "暂无"
    loc_hint = "、".join(l.name for l in locs[:5]) if locs else "暂无"

    item_result, ierr = await _safe_skill_call(engine, ai_client, "items_generate", {
        "title": proj.title,
        "world_info": _build_world_info(proj),
        "user_prompt": f"请为《{proj.title}》生成5-8个物品，至少1个关键剧情道具。已有角色：{char_hint}。已有地点：{loc_hint}。物品应与角色身份、能力以及地点环境相匹配。",
    }, "物品")
    if ierr:
        return ierr

    items = item_result.get("json") or []
    if isinstance(items, list):
        for it in items[:10]:
            if isinstance(it, dict) and it.get("name"):
                db.add(Item(
                    project_id=pid,
                    name=str(it.get("name", ""))[:100],
                    category=str(it.get("category", "装备"))[:50],
                    rarity=str(it.get("rarity", "common"))[:20],
                    item_type=str(it.get("item_type", ""))[:50],
                    description=str(it.get("description", ""))[:2000],
                    is_key_item=1 if it.get("is_key_item") else 0,
                    status="stored",
                    source="ai",
                ))
        await db.commit()
    task.items_done = 1
    return None


async def _step_outline(db, task, pid, proj, engine, ai_client):
    """步骤8：大纲生成（默认3章，用户可选）。

    传递完整的上下文变量，兼容用户自定义模板中可能使用的各种变量名：
    - 标准变量：world_info, characters_info, synopsis, chapter_count, user_prompt
    - 用户自定义变量：time_period, location, atmosphere, rules, theme,
      narrative_perspective, title, genre, mcp_references, requirements
    """
    from app.models.outline import Outline
    from app.models.chapter import Chapter
    from app.models.world import WorldSetting
    from app.models.character import Character

    task.status_message = "生成大纲..."
    await db.commit()

    chapter_count = str(task.chapter_count or 3)
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == pid))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()

    # 世界信息：完整四维度 + 最近10条详细设定
    world_info_complete = _build_world_info(proj)
    if worlds:
        detail_text = "\n".join([f"- {w.name}({w.category or '其他'})：{w.content[:150]}" for w in worlds[:10]])
        world_info_complete += f"\n\n【详细设定】\n{detail_text}"

    # 角色信息：分层策略（核心角色全量、配角中等、远处仅名字）
    char_parts = []
    for c in chars[:15]:
        is_core = c.role in ("主角", "反派")
        if is_core:
            lines = [f"- {c.name}（{c.role or '角色'}，{c.gender or ''}，{c.age or '?'}岁）"]
            if c.identity: lines.append(f"  身份：{c.identity}")
            if c.personality: lines.append(f"  性格：{c.personality}")
            if c.background: lines.append(f"  背景：{c.background}")
            if c.story_goal: lines.append(f"  目标：{c.story_goal}")
            if c.motivation: lines.append(f"  动机：{c.motivation}")
            if c.weakness: lines.append(f"  弱点：{c.weakness}")
            if c.occupation: lines.append(f"  职业：{c.occupation}")
            if c.ability: lines.append(f"  能力：{c.ability}")
            char_parts.append("\n".join(lines))
        else:
            # 配角：中等信息
            lines = [f"- {c.name}（{c.role or '配角'}，{c.gender or ''}）"]
            if c.personality: lines.append(f"  性格：{c.personality[:120]}")
            if c.occupation: lines.append(f"  职业：{c.occupation}")
            if c.story_goal: lines.append(f"  目标：{c.story_goal[:80]}")
            char_parts.append("\n".join(lines))
    if len(chars) > 15:
        char_parts.append(f"... 还有 {len(chars) - 15} 个角色（可用工具查询详情）")
    chars_info = "\n\n".join(char_parts) if char_parts else "暂无"

    result, oerr = await _safe_skill_call(engine, ai_client, "outline_create", {
        # 标准变量（文件模板用）
        "world_info": world_info_complete,
        "characters_info": chars_info,
        "synopsis": proj.synopsis or "暂无简介",
        "chapter_count": chapter_count,
        "user_prompt": f"请为《{proj.title}》生成{chapter_count}章大纲。如需确认角色关系、组织详情、伏笔状态，可使用工具查询。",
        # 用户自定义模板可能用的变量
        "title": proj.title,
        "genre": proj.genre or "网文",
        "theme": proj.genre or "网文",
        "narrative_perspective": proj.narrative_pov or "第三人称",
        "time_period": proj.world_time_period or "",
        "location": proj.world_location or "",
        "atmosphere": proj.world_atmosphere or "",
        "rules": proj.world_rules or "",
        "mcp_references": "",
        "requirements": "",
    }, "大纲",
        tools=get_chapter_tools(),
        tool_executor=make_tool_executor(db, pid, int(chapter_count) + 1),
    )
    if oerr:
        return oerr

    outlines_data = result.get("json") or []
    added = 0
    created_outline_objs = []
    if isinstance(outlines_data, list):
        for idx, item in enumerate(outlines_data):
            if isinstance(item, dict):
                ch_num = item.get("chapter_number")
                if not isinstance(ch_num, int) or ch_num < 1:
                    ch_num = idx + 1
                o = Outline(
                    project_id=pid,
                    chapter_number=ch_num,
                    title=str(item.get("title", f"第{ch_num}章"))[:200],
                    summary=str(item.get("summary", ""))[:2000],
                    key_points=item.get("key_points", []) if isinstance(item.get("key_points"), list) else [],
                    emotion=str(item.get("emotion", ""))[:100],
                    goal=str(item.get("goal", ""))[:200],
                    structure=item,
                )
                db.add(o)
                created_outline_objs.append(o)
                added += 1
        if added:
            await db.flush()

            # 1对1模式：自动为每条大纲创建对应章节
            if (proj.outline_mode or "one_to_one") == "one_to_one":
                for o in created_outline_objs:
                    existing_ch = (await db.execute(
                        select(Chapter).where(
                            Chapter.project_id == pid,
                            Chapter.chapter_number == o.chapter_number,
                        )
                    )).scalars().first()
                    if existing_ch:
                        continue
                    ch = Chapter(
                        project_id=pid,
                        chapter_number=o.chapter_number,
                        title=o.title,
                        summary=o.summary[:200] if o.summary else "",
                        status="draft",
                        outline_id=None,
                        sub_index=1,
                        generation_mode="one_to_one",
                    )
                    db.add(ch)
            await db.commit()
            task.outline_done = 1
            task.status_message = f"已生成 {added} 章大纲"
    return None


async def _step_validate_outline(db, task, pid, proj, engine, ai_client):
    """验证大纲：检查大纲中涉及的角色和组织是否都已创建，未创建的自动补充。"""
    task.status_message = "验证大纲完整性..."
    await db.commit()

    from app.services.outline_validation_service import validate_outline_entities, build_world_context
    world_ctx = build_world_context(proj)
    count = await validate_outline_entities(db, pid, proj.title, proj.genre or "网文", world_ctx, engine, ai_client)

    task.status_message = f"大纲验证完成（补全 {count} 个实体）" if count else "大纲验证通过"
    await db.commit()
    return None


# 步骤执行器映射
STEP_EXECUTORS = {
    "world": _step_world,
    "locations": _step_locations,
    "items": _step_items,
    "career": _step_career,
    "characters": _step_characters,
    "org": _step_org,
    "relations": _step_relations,
    "outline": _step_outline,
    "validate_outline": _step_validate_outline,
}


async def _run_init_task(task_id: int, resume_from: str = None):
    """后台执行：8 步生成流水线。

    重试策略：每个步骤内部重试 3 次，全部失败后停止整个任务，
    标记 status=failed + failed_step，用户可通过 resume API 从失败步骤继续。
    """
    async with async_session() as db:
        task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
        if not task:
            return
        pid = task.project_id
        proj = (await db.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
        if not proj:
            task.status = "failed"
            task.error = "项目不存在"
            await db.commit()
            return

        task.status = "running"
        task.status_message = "开始生成..."
        task.failed_step = ""
        await db.commit()

        engine = SkillEngine(db, task.user_id)
        ai_client = await AIClient.from_user_config(db, task.user_id)

        # 确定起始步骤（支持 resume）
        start_idx = 0
        if resume_from and resume_from in STEP_ORDER:
            start_idx = STEP_ORDER.index(resume_from)

        for idx in range(start_idx, len(INIT_STEPS)):
            step_key, step_label, step_progress, done_field = INIT_STEPS[idx]

            # 检查是否被取消
            await db.refresh(task)
            if task.cancel_requested:
                task.status = "cancelled"
                task.status_message = "任务已取消"
                task.updated_at = datetime.utcnow()
                await db.commit()
                return

            # 跳过已完成的步骤（resume 时）
            if getattr(task, done_field, 0) == 1:
                continue

            task.status_message = f"{step_label}..."
            task.progress = step_progress
            await db.commit()

            executor = STEP_EXECUTORS[step_key]
            try:
                err = await executor(db, task, pid, proj, engine, ai_client)
            except Exception as e:
                err = f"{step_label}: {e}"

            if err:
                # 步骤失败：停止整个任务
                task.status = "failed"
                task.failed_step = step_key
                task.error = err[:1000]
                task.status_message = f"{step_label}生成失败，可点击重试从本步骤继续"
                task.progress = step_progress
                task.updated_at = datetime.utcnow()
                await db.commit()
                return

            task.progress = INIT_STEPS[idx + 1][2] if idx + 1 < len(INIT_STEPS) else 100
            await db.commit()

        # 全部完成
        task.status = "completed"
        task.status_message = "生成完成"
        task.progress = 100
        task.failed_step = ""
        task.updated_at = datetime.utcnow()
        await db.commit()


@router.post("/{project_id}/init-task")
async def create_init_task(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """提交项目初始化后台任务，立即返回任务ID。"""
    proj = (await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "项目不存在")
    chapter_count = int(req.get("chapter_count", 3))
    if chapter_count not in (3, 5, 10):
        chapter_count = 3
    task = ProjectInitTask(
        project_id=project_id, user_id=user.id, task_type="init",
        status="pending", status_message="排队中...",
        chapter_count=chapter_count,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    asyncio.create_task(_run_init_task(task.id))
    return {"task_id": task.id, "project_id": project_id, "status": "pending"}


@router.get("/init-tasks/failed")
async def get_failed_init_tasks(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """获取当前用户的失败初始化任务列表。"""
    result = await db.execute(
        select(ProjectInitTask)
        .where(ProjectInitTask.user_id == user.id, ProjectInitTask.status == "failed")
        .order_by(ProjectInitTask.created_at.desc())
        .limit(10)
    )
    tasks = result.scalars().all()
    return [task.to_dict() for task in tasks]


@router.get("/init-task/{task_id}/status")
async def get_init_task_status(task_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """查询初始化任务进度。"""
    task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()


@router.post("/init-task/{task_id}/resume")
async def resume_init_task(task_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """从失败的步骤继续执行初始化任务。"""
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"[resume] 收到恢复请求: task_id={task_id}, user_id={user.id}")

    task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
    if not task:
        logger.warning(f"[resume] 任务不存在: task_id={task_id}")
        raise HTTPException(404, "任务不存在")

    logger.info(f"[resume] 任务状态: status={task.status}, failed_step={task.failed_step}, project_id={task.project_id}")

    if task.status not in ("failed", "completed"):
        logger.warning(f"[resume] 任务状态不允许恢复: status={task.status}")
        raise HTTPException(400, f"任务当前状态为 {task.status}，无需恢复")

    resume_from = task.failed_step or None
    task.status = "running"
    task.error = ""
    task.failed_step = ""
    await db.commit()

    logger.info(f"[resume] 启动后台任务: task_id={task_id}, resume_from={resume_from}")
    asyncio.create_task(_run_init_task(task_id, resume_from=resume_from))

    return {"task_id": task_id, "status": "running", "resume_from": resume_from}


@router.post("/init-task/{task_id}/cancel")
async def cancel_init_task(task_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """取消初始化任务。"""
    task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status in ("pending", "running"):
        task.cancel_requested = 1
        # pending 任务可直接置 cancelled
        if task.status == "pending":
            task.status = "cancelled"
            task.status_message = "任务已取消"
        task.updated_at = datetime.utcnow()
        await db.commit()
    return {"task_id": task_id, "status": task.status}
