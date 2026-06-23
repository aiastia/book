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
from sqlalchemy import select


# 角色英文 role → 中文映射
ROLE_MAP = {
    "protagonist": "主角", "main": "主角", "主角": "主角",
    "antagonist": "反派", "villain": "反派", "反派": "反派",
    "supporting": "配角", "side": "配角", "配角": "配角",
    "minor": "路人", "passby": "路人", "路人": "路人",
}

# 初始化步骤定义（名称, 进度, done 字段名）
# 顺序优化（方案B）：世界观 → 职业 → 组织 → 角色 → 关系 → 地点 → 物品 → 大纲
# 组织提前到角色之前，这样角色生成时 AI 可指定所属组织，关联更可靠
INIT_STEPS = [
    ("world", "世界观", 8, "world_done"),
    ("career", "职业体系", 16, "career_done"),
    ("org", "组织势力", 26, "org_done"),
    ("characters", "角色", 36, "characters_done"),
    ("relations", "角色关系", 46, "relations_done"),
    ("locations", "地点地图", 58, "locations_done"),
    ("items", "物品道具", 68, "items_done"),
    ("outline", "大纲", 82, "outline_done"),
]
STEP_ORDER = [s[0] for s in INIT_STEPS]


async def _safe_skill_call(engine, ai_client, skill_name, context, label="步骤", max_retries=3):
    """带重试的 skill 调用。

    每次调用内部含 execute_skill 的 JSON 重试（3次），
    这里额外重试 max_retries 次，处理连接级错误。
    """
    import logging
    logger = logging.getLogger(__name__)
    last_err = None
    for attempt in range(max_retries):
        try:
            result = await engine.execute_skill(skill_name, ai_client, context)
            if not result.get("error"):
                return result, None
            last_err = result.get("error")
        except Exception as e:
            last_err = str(e)
        if attempt < max_retries - 1:
            delay = min(2 * (attempt + 1), 10)
            logger.info(f"[init] {label}第{attempt+1}次重试，等待{delay}秒...")
            await asyncio.sleep(delay)
    return None, f"{label}失败（已重试{max_retries}次）: {last_err}"


from app.core.database import get_db, async_session
from app.core.auth import get_current_user
from app.models.project import Project
from app.models.project_init_task import ProjectInitTask
from app.skills.engine import SkillEngine
from app.core.ai_client import AIClient

router = APIRouter(prefix="/api/projects", tags=["项目初始化"])


def _map_role(raw_role: str, default="配角") -> str:
    """将英文 role_type 映射为中文。"""
    if not raw_role:
        return default
    key = str(raw_role).strip().lower()
    return ROLE_MAP.get(key, ROLE_MAP.get(str(raw_role).strip(), default))


async def _step_world(db, task, pid, proj, engine, ai_client):
    """步骤1：核心世界观 + 详细设定"""
    from app.models.world import WorldSetting

    task.status_message = "生成核心世界观..."
    task.progress = 5
    await db.commit()

    result, werr = await _safe_skill_call(engine, ai_client, "world_core_generate", {
        "genre": proj.genre or "网文", "title": proj.title, "synopsis": proj.synopsis or "暂无",
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
        "world_info": f"时间={proj.world_time_period}\n地点={proj.world_location}\n规则={proj.world_rules}",
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
    """步骤2：职业体系"""
    from app.models.career import Career

    task.status_message = "生成职业体系..."
    await db.commit()

    career_result, cerr = await _safe_skill_call(engine, ai_client, "career_system_generation", {
        "title": proj.title, "genre": proj.genre or "网文",
        "world_info": f"规则：{proj.world_rules or ''}",
        "user_prompt": f"请为《{proj.title}》生成职业体系。",
    }, "职业")
    if cerr:
        return cerr

    careers_data = career_result.get("json")
    # 兼容多种格式：数组 / {main_careers, sub_careers} / {careers: [...]} / 裸 dict
    careers_list = []
    if isinstance(careers_data, list):
        careers_list = careers_data
    elif isinstance(careers_data, dict):
        for key in ("main_careers", "sub_careers", "careers"):
            items = careers_data.get(key, [])
            if isinstance(items, list):
                careers_list.extend(items)
        if not careers_list and careers_data.get("name"):
            careers_list = [careers_data]

    for item in careers_list[:8]:
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
    """步骤4：角色批量生成（含主角/配角/反派，关联已有组织）"""
    from app.models.character import Character
    from app.models.organization import Organization

    task.status_message = "生成角色..."
    await db.commit()

    # 获取已有组织列表，传给 AI 让角色直接关联组织
    orgs = (await db.execute(select(Organization).where(Organization.project_id == pid))).scalars().all()
    org_info = "、".join(o.name for o in orgs[:10]) if orgs else "暂无"
    # 获取已有职业体系
    from app.models.career import Career
    careers = (await db.execute(select(Career).where(Career.project_id == pid))).scalars().all()
    career_info = "、".join(c.name for c in careers[:8]) if careers else "暂无"

    result, cerr = await _safe_skill_call(engine, ai_client, "characters_batch_generation", {
        "genre": proj.genre or "网文", "title": proj.title,
        "synopsis": proj.synopsis or "暂无简介", "count": "5",
        "existing_characters": "暂无",
        "world_info": f"{proj.world_location or ''} {proj.world_rules or ''}",
        "user_prompt": f"""请生成5个角色（必须包含1个主角、1个反派、其余配角）。
已有组织：{org_info}。角色如果属于某个组织，请在 organization_memberships 中填写组织名。
已有职业体系：{career_info}。角色职业应参考已有职业体系。""",
    }, "角色")
    if cerr:
        return cerr

    chars_data = result.get("json") or []
    added = 0
    if not isinstance(chars_data, list):
        return "角色生成返回格式错误"

    existing_names = set()
    existing_chars = (await db.execute(select(Character.name).where(Character.project_id == pid))).all()
    existing_names = {r[0] for r in existing_chars}

    # 保存原始 AI 数据（用于后续组织关联）
    raw_chars = []

    for item in chars_data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        char_name = str(item.get("name", "")).strip()
        if item.get("is_organization") or item.get("is_org"):
            continue
        if char_name in existing_names:
            continue
        existing_names.add(char_name)

        # role 字段：支持 role_type（英文）映射为中文
        raw_role = item.get("role", item.get("role_type", item.get("character_role", "")))
        mapped_role = _map_role(raw_role)

        # traits 数组 → ability 字符串
        traits = item.get("traits", item.get("abilities_list", []))
        if isinstance(traits, list):
            ability_text = "、".join(str(t) for t in traits if t)
        else:
            ability_text = ""

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
            occupation=str(item.get("occupation", item.get("profession", item.get("career", ""))))[:200],
            speech_style=str(item.get("speech_style", item.get("dialogue_style", item.get("speech_pattern", ""))))[:200],
            arc_type=str(item.get("arc_type", item.get("character_arc", "")))[:200],
            character_change=str(item.get("character_change", item.get("transformation", "")))[:2000],
        )
        db.add(char)
        raw_chars.append((char, item))
        added += 1

    if added:
        await db.flush()  # 拿到 char.id
        # 处理角色-组织关联（organization_memberships）
        await _link_org_memberships(db, pid, raw_chars)
        await db.commit()
        task.characters_done = 1
        task.status_message = f"已生成 {added} 个角色"
    else:
        return "角色生成失败：没有有效角色"
    return None


async def _link_org_memberships(db, pid, raw_chars):
    """从 AI 返回的数据中提取组织关联，写入 Character.organization_id"""
    from app.models.organization import Organization, OrganizationMember
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
                char.organization_id = org_id
                # 同时写入 OrganizationMember（避免重复）
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
                        role=item.get("org_role", "成员")[:50] if isinstance(item.get("org_role"), str) else "成员",
                        status="active",
                    ))
                break  # 一个角色只关联第一个匹配的组织


async def _step_relations(db, task, pid, proj, engine, ai_client):
    """步骤4：角色关系图谱"""
    from app.models.character import Character, CharacterRelation

    task.status_message = "生成角色关系..."
    await db.commit()

    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    if len(chars) < 2:
        task.relations_done = 1
        return None

    char_list = "、".join(f"{c.name}（{c.role or '角色'}）" for c in chars[:10])
    rel_result, rerr = await _safe_skill_call(engine, ai_client, "character_relations_generate", {
        "title": proj.title, "characters_info": char_list,
    }, "关系图谱")
    if rerr:
        return rerr

    rels = rel_result.get("json") or []
    if isinstance(rels, list):
        name_to_id = {c.name: c.id for c in chars}
        added_rels = 0
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            from_name = rel.get("from", "")
            to_name = rel.get("to", "")
            from_id = name_to_id.get(from_name)
            to_id = name_to_id.get(to_name)
            if from_id and to_id and from_id != to_id:
                db.add(CharacterRelation(
                    project_id=pid,
                    from_character_id=from_id,
                    to_character_id=to_id,
                    relation_type=str(rel.get("relation_type", "关系"))[:100],
                    category=str(rel.get("category", "social"))[:50],
                    intimacy=int(rel.get("intimacy", 50)) if str(rel.get("intimacy", "50")).lstrip("-").isdigit() else 50,
                    description=str(rel.get("description", ""))[:500],
                ))
                added_rels += 1
        if added_rels:
            await db.commit()
    task.relations_done = 1
    return None


async def _step_org(db, task, pid, proj, engine, ai_client):
    """步骤5：组织势力生成"""
    from app.models.organization import Organization

    task.status_message = "生成组织势力..."
    await db.commit()

    org_result, oerr = await _safe_skill_call(engine, ai_client, "organization_generate", {
        "title": proj.title, "genre": proj.genre or "网文",
        "world_info": f"{proj.world_location or ''} {proj.world_rules or ''}",
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
            db.add(Organization(project_id=pid,
                name=str(item.get("name", ""))[:100],
                org_type=str(item.get("org_type", item.get("organization_type", item.get("type", ""))))[:50],
                description=str(item.get("description", item.get("background", "")))[:2000],
                power_value=pv,
                location=str(item.get("location", ""))[:200],
                motto=str(item.get("motto", ""))[:200],
                color=str(item.get("color", ""))[:20]))
    await db.commit()
    task.org_done = 1
    return None


async def _step_locations(db, task, pid, proj, engine, ai_client):
    """步骤6：地点地图"""
    from app.models.location import Location

    task.status_message = "生成地点地图..."
    await db.commit()

    loc_result, lerr = await _safe_skill_call(engine, ai_client, "locations_generate", {
        "title": proj.title, "world_info": f"{proj.world_location or ''} {proj.synopsis or ''}",
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
    """步骤7：物品道具"""
    from app.models.item import Item

    task.status_message = "生成物品道具..."
    await db.commit()

    item_result, ierr = await _safe_skill_call(engine, ai_client, "items_generate", {
        "title": proj.title, "world_info": f"规则：{proj.world_rules or ''} 简介：{proj.synopsis or ''}",
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
    """步骤8：大纲生成（默认3章，用户可选）"""
    from app.models.outline import Outline
    from app.models.chapter import Chapter
    from app.models.world import WorldSetting
    from app.models.character import Character

    task.status_message = "生成大纲..."
    await db.commit()

    chapter_count = str(task.chapter_count or 3)
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == pid))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or f"{proj.world_location} {proj.world_rules}"
    chars_info = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"

    result, oerr = await _safe_skill_call(engine, ai_client, "outline_create", {
        "world_info": world_info, "characters_info": chars_info,
        "synopsis": proj.synopsis or "暂无简介", "chapter_count": chapter_count,
        "user_prompt": f"请为《{proj.title}》生成{chapter_count}章大纲",
    }, "大纲")
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


# 步骤执行器映射
STEP_EXECUTORS = {
    "world": _step_world,
    "career": _step_career,
    "characters": _step_characters,
    "relations": _step_relations,
    "org": _step_org,
    "locations": _step_locations,
    "items": _step_items,
    "outline": _step_outline,
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
    task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in ("failed", "completed"):
        raise HTTPException(400, f"任务当前状态为 {task.status}，无需恢复")
    resume_from = task.failed_step or None
    task.status = "running"
    task.error = ""
    task.failed_step = ""
    await db.commit()
    asyncio.create_task(_run_init_task(task_id, resume_from=resume_from))
    return {"task_id": task_id, "status": "running", "resume_from": resume_from}
