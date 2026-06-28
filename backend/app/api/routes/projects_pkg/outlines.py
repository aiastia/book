"""大纲：生成 / CRUD / 续写 / 展开"""

import asyncio
import json
import logging

from app.api.routes.projects_pkg.base import *
from app.core.database import async_session
from app.services.chapter_tools import get_chapter_tools, make_tool_executor
from app.services.outline_validation_service import validate_outline_entities

logger = logging.getLogger(__name__)


router = make_router()

# 组织名关键词：用于兜底判断 characters 中的名称是否实为组织
_ORG_KEYWORDS = (
    "议会",
    "帮",
    "派",
    "门",
    "宗",
    "盟",
    "阁",
    "会",
    "部",
    "团",
    "社",
    "局",
    "庭",
    "族",
    "学院",
    "教会",
    "帝国",
    "王国",
    "殿",
    "堂",
    "塔",
)


def _extract_names(lst: list) -> list:
    """从列表中提取 (名称, 类型) 对，兼容字符串和 {name:...} 两种格式。"""
    result = []
    for ch in lst or []:
        if isinstance(ch, dict):
            name = (ch.get("name") or "").strip()
            ctype = (ch.get("type") or "").strip().lower()
        elif isinstance(ch, str):
            name = ch.strip()
            ctype = ""
        else:
            continue
        if name:
            result.append((name, ctype))
    return result


def _dedup(lst: list) -> list:
    """去重保序。"""
    seen, out = set(), []
    for x in lst:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _clean_scene(scene) -> dict:
    """规范化单个场景对象：确保含 scene_title/scene_desc/emotion。"""
    if not isinstance(scene, dict):
        s = str(scene).strip()
        return {"scene_title": s, "scene_desc": "", "emotion": ""} if s else {}
    title = (scene.get("scene_title") or scene.get("title") or "").strip()
    desc = (scene.get("scene_desc") or scene.get("description") or scene.get("desc") or "").strip()
    emo = (scene.get("emotion") or scene.get("emotional_tone") or "").strip()
    if not (title or desc or emo):
        return {}
    return {"scene_title": title or "场景", "scene_desc": desc, "emotion": emo}


def _separate_chars_orgs(raw_chars: list, raw_orgs: list, char_names: set, org_names: set) -> tuple:
    """分离角色与组织：把误塞进 characters 的组织移到 organizations。

    判断逻辑（优先级从高到低）：
    1. 明确标记 type=organization → 组织
    2. 在已知组织名集合中 → 组织
    3. 不在已知角色集合 + 含组织关键词（议会/帮/派...）→ 组织
    4. 其余 → 角色
    """
    char_pairs = _extract_names(raw_chars)
    org_pairs = _extract_names(raw_orgs)

    final_orgs = [name for name, _ in org_pairs]
    final_chars = []

    for name, ctype in char_pairs:
        if ctype == "organization":
            final_orgs.append(name)
            continue
        if name in org_names:
            final_orgs.append(name)
            continue
        # 已知角色集合不为空时，不在其中的 + 含组织关键词 → 归为组织
        if char_names and name not in char_names and any(kw in name for kw in _ORG_KEYWORDS):
            final_orgs.append(name)
            continue
        final_chars.append(name)

    return _dedup(final_chars), _dedup(final_orgs)


def _build_outline(
    project_id: int,
    item: dict,
    offset: int = 0,
    index: int = 0,
    char_names: set = None,
    org_names: set = None,
) -> Outline:
    """从 AI 返回的 item 构造 Outline 对象（复用）。

    index 用于 AI 没返回 chapter_number 时自动编号（1-based）。
    char_names/org_names 用于兜底过滤：AI 可能把组织塞进 characters，
    或把临时称呼（如"男孩"）当成角色，这里自动校正。
    """
    ch_num = item.get("chapter_number")
    if not isinstance(ch_num, int) or ch_num < 1:
        ch_num = index + 1  # AI 没返回或非法时，用序号

    # ===== 兜底清洗 =====
    raw_chars = item.get("characters", []) if isinstance(item.get("characters"), list) else []
    raw_orgs = item.get("organizations", []) if isinstance(item.get("organizations"), list) else []
    final_chars, final_orgs = _separate_chars_orgs(
        raw_chars, raw_orgs, char_names or set(), org_names or set()
    )

    # 安全网：如果 AI 明确返回了角色但被过滤光了，保留 AI 原始值
    if not final_chars and raw_chars:
        raw_names = [
            c if isinstance(c, str) else c.get("name", "")
            for c in raw_chars
            if isinstance(c, (str, dict))
        ]
        raw_names = [n.strip() for n in raw_names if n.strip()]
        if raw_names:
            logger.warning(f"[outline] 第{ch_num}章角色被过滤为空，保留AI原始值: {raw_names}")
            final_chars = raw_names

    # 规范化场景：过滤掉只有标题没有描述的空场景
    raw_scenes = item.get("scenes", []) if isinstance(item.get("scenes"), list) else []
    clean_scenes = [c for c in (_clean_scene(sc) for sc in raw_scenes) if c]

    # 回写清洗后的值到 item（structure 会同步更新）
    item = dict(item)  # 浅拷贝，不修改原始
    item["characters"] = final_chars
    item["organizations"] = final_orgs
    item["scenes"] = clean_scenes

    # 警告：大纲缺少角色（AI 可能忽略了 characters 字段）
    if not final_chars:
        logger.warning(f"[outline] 第{ch_num}章大纲缺少角色（characters 为空），请检查 AI 输出")

    return Outline(
        project_id=project_id,
        chapter_number=ch_num + offset,
        title=str(item.get("title", f"第{ch_num}章"))[:200],
        summary=str(item.get("summary", ""))[:2000],
        scenes=clean_scenes,
        characters=final_chars,
        key_points=item.get("key_points", []) if isinstance(item.get("key_points"), list) else [],
        emotion=str(item.get("emotion", ""))[:100],
        goal=str(item.get("goal", ""))[:200],
        structure=item,
    )


def _format_foreshadows_for_outline(foreshadows: list, start_chapter: int, end_chapter: int) -> str:
    """将伏笔按目标章节分组格式化，让 AI 知道哪些必须在本次大纲中回收。

    分组：
    - 🎯 本次必须回收（target 在 [start, end] 内）
    - ⚠️ 已超期未回收（target < start）
    - ⏰ 下一批即将到期（target 在 (end, end+10]）
    - 📋 待回收（target > end+10 或未指定）
    - 🌱 待埋入（status=pending，plant_chapter 在本次范围内）
    """
    if not foreshadows:
        return "暂无伏笔"

    must = []  # 本次必须回收
    overdue = []  # 超期
    upcoming = []  # 下一批
    future = []  # 远期
    plant_now = []  # 待埋入

    for f in foreshadows:
        target = f.target_resolve_chapter_number
        plant = f.plant_chapter_number

        # 待埋入的伏笔（状态 pending，埋入计划在本批次范围）
        if f.status == "pending" and plant and start_chapter <= plant <= end_chapter:
            plant_now.append(f)
            continue

        if target:
            if start_chapter <= target <= end_chapter:
                must.append(f)
            elif target < start_chapter:
                overdue.append(f)
            elif target <= end_chapter + 10:
                upcoming.append(f)
            else:
                future.append(f)
        else:
            future.append(f)

    parts = []

    if must:
        lines = [f"🎯 【本次必须回收（第{start_chapter}-{end_chapter}章）】"]
        for f in must:
            lines.append(
                f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章，优先:{f.priority or 5}）"
            )
        parts.append("\n".join(lines))

    if overdue:
        lines = ["⚠️ 【已超期未回收（请尽快安排）】"]
        for f in overdue:
            lines.append(
                f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章，已超期）"
            )
        parts.append("\n".join(lines))

    if upcoming:
        lines = [f"⏰ 【下一批即将到期（第{end_chapter + 10}章前）】"]
        for f in upcoming:
            lines.append(
                f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章）"
            )
        parts.append("\n".join(lines))

    if plant_now:
        lines = ["🌱 【本次应埋入的伏笔】"]
        for f in plant_now:
            lines.append(
                f"  - {f.title}：{f.content or ''}（计划在第{f.plant_chapter_number}章埋入，第{f.target_resolve_chapter_number or '?'}章回收）"
            )
        parts.append("\n".join(lines))

    if future:
        lines = ["📋 【远期伏笔（可铺垫，不必立即回收）】"]
        for f in future:
            target_str = (
                f"目标第{f.target_resolve_chapter_number}章"
                if f.target_resolve_chapter_number
                else "未指定回收章节"
            )
            lines.append(f"  - {f.title}：{f.content or ''}（{target_str}）")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else "暂无伏笔"


async def _project_context(
    db: AsyncSession,
    project_id: int,
    project: Project,
    use_tools: bool = False,
    collect_only: bool = False,
) -> dict:
    """收集项目的世界观/角色/组织上下文信息。

    use_tools=True:  精简上下文（角色仅骨架），AI 用工具查询世界观/组织，但角色信息已提供无需查询。
    collect_only=True: 仅骨架（角色仅姓名+身份），AI 需用工具查询一切（包括角色详情）。用于两阶段收集。"""
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )

    # 世界设定：核心四维度始终发送；详细设定仅非工具/非收集模式发送
    core_parts = []
    if project.world_time_period:
        core_parts.append(f"时间背景：{project.world_time_period}")
    if project.world_location:
        core_parts.append(f"地理位置：{project.world_location}")
    if project.world_atmosphere:
        core_parts.append(f"氛围基调：{project.world_atmosphere}")
    if project.world_rules:
        core_parts.append(f"世界规则：{project.world_rules}")
    core = "\n".join(core_parts)

    if collect_only:
        world_info = "【核心世界观】\n" + (core or "暂无")
    elif use_tools:
        tool_hint = (
            "\n\n💡 世界设定条目（地理/历史/文化等）、组织详情、地点信息等辅助资料可通过工具查询。"
            "角色信息已提供，无需查询。建议先调用 list_available_entities 了解可查内容。"
        )
        world_info = "【核心世界观】\n" + (core or "暂无") + tool_hint
    else:
        detail_items = "\n".join(
            [f"- {w.name}({w.category or ''})：{w.content[:150]}" for w in worlds[:10]]
        )
        world_info = (
            ("【核心世界观】\n" + core + "\n【详细设定】\n" + detail_items)
            if detail_items
            else (core or "暂无")
        )

    # 角色：collect_only/工具模式下仅发名字+角色+身份（一行），详细用工具查；非工具模式分层注入
    char_parts = []
    if collect_only or use_tools:
        for c in chars:
            info = f"- {c.name}（{c.role}"
            if c.identity:
                info += f"，{c.identity[:60]}"
            info += "）"
            char_parts.append(info)
    else:
        recent_char_names = set()
        try:
            recent_outlines = (
                (
                    await db.execute(
                        select(Outline)
                        .where(Outline.project_id == project_id)
                        .order_by(Outline.chapter_number.desc())
                        .limit(5)
                    )
                )
                .scalars()
                .all()
            )
            for o in recent_outlines:
                if o.characters and isinstance(o.characters, list):
                    for c in o.characters:
                        recent_char_names.add(
                            str(c).strip() if isinstance(c, str) else c.get("name", "")
                        )
        except Exception:
            pass

        for c in chars:
            is_core = c.role in ("主角", "反派")
            is_recent = c.name in recent_char_names or not recent_char_names
            if is_core:
                lines = [f"- {c.name}（{c.role}，{c.gender or ''}，{c.age or '?'}岁）"]
                if c.identity:
                    lines.append(f"  身份：{c.identity}")
                if c.personality:
                    lines.append(f"  性格：{c.personality}")
                if c.background:
                    lines.append(f"  背景：{c.background}")
                if c.story_goal:
                    lines.append(f"  目标：{c.story_goal}")
                if c.motivation:
                    lines.append(f"  动机：{c.motivation}")
                if c.weakness:
                    lines.append(f"  弱点：{c.weakness}")
                if c.ability:
                    lines.append(f"  能力：{c.ability}")
                char_parts.append("\n".join(lines))
            elif is_recent:
                lines = [f"- {c.name}（{c.role}，{c.gender or ''}）"]
                if c.personality:
                    lines.append(f"  性格：{c.personality[:120]}")
                if c.story_goal:
                    lines.append(f"  目标：{c.story_goal[:80]}")
                char_parts.append("\n".join(lines))
            else:
                char_parts.append(f"- {c.name}（{c.role}）")
    chars_info = "\n\n".join(char_parts) if char_parts else "暂无"

    # 组织：非工具模式全量；工具/收集模式仅发送简要列表
    if not use_tools and not collect_only:
        orgs_info = (
            "\n".join(
                [
                    f"- {o.name}（{o.org_type or '组织'}，势力值{o.power_value or 50}）：{o.description or ''}"
                    for o in orgs
                ]
            )
            or "暂无"
        )
    else:
        orgs_info = "\n".join([f"- {o.name}" for o in orgs]) or "暂无"

    char_names = {c.name for c in chars}
    org_names = {o.name for o in orgs}
    char_roles = {c.name: c.role for c in chars}

    # 物品与地点（大纲/章节生成时注入，让 AI 知道有哪些可用道具和场景）
    items = (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    if collect_only:
        items_info = (
            "\n".join([f"- {it.name}（{it.category or '道具'}）" for it in items]) or "暂无"
        )
    else:
        items_info = (
            "\n".join(
                [
                    f"- {it.name}（{it.category or '道具'}，{'⭐关键道具' if it.is_key_item else '普通'}）：{it.description[:120] if it.description else ''}"
                    for it in items
                ]
            )
            or "暂无"
        )

    locations = (
        (await db.execute(select(Location).where(Location.project_id == project_id)))
        .scalars()
        .all()
    )
    if collect_only:
        locations_info = (
            "\n".join([f"- {loc.name}（{loc.location_type or '地点'}）" for loc in locations])
            or "暂无"
        )
    else:
        locations_info = (
            "\n".join(
                [
                    f"- {loc.name}（{loc.location_type or '地点'}，危险等级={loc.danger_level or 'safe'}）：{loc.description[:120] if loc.description else ''}"
                    for loc in locations
                ]
            )
            or "暂无"
        )

    return {
        "world_info": world_info,
        "characters_info": chars_info,
        "organizations_info": orgs_info,
        "items_info": items_info,
        "locations_info": locations_info,
        "char_names": char_names,
        "org_names": org_names,
        "char_roles": char_roles,
        "time_period": project.world_time_period or "",
        "location": project.world_location or "",
        "atmosphere": project.world_atmosphere or "",
        "rules": project.world_rules or "",
    }


def _validate_collection(tool_call_history: list[dict], ctx: dict) -> dict:
    """校验 Phase 1 信息收集是否覆盖关键维度。

    检查项：世界观详情、主角档案、反派档案（如有）、至少一个地点。
    返回 {"complete": bool, "missing": [str], "called_tools": [str], "queried_characters": [str]}
    """
    called_tools: set[str] = set()
    queried_characters: set[str] = set()

    for call in tool_call_history:
        name = call.get("name", "")
        called_tools.add(name)
        args = call.get("arguments", {})
        if name == "query_character":
            char_name = args.get("name", "")
            if char_name:
                queried_characters.add(char_name)

    missing: list[str] = []

    if "query_world_setting" not in called_tools:
        missing.append("世界观详细信息")

    char_roles: dict[str, str] = ctx.get("char_roles", {})
    protagonists = [name for name, role in char_roles.items() if role == "主角"]
    antagonists = [name for name, role in char_roles.items() if role == "反派"]

    for p in protagonists:
        if p not in queried_characters:
            missing.append(f"主角「{p}」的完整档案")
    for a in antagonists:
        if a not in queried_characters:
            missing.append(f"反派「{a}」的完整档案")

    if "query_location" not in called_tools:
        missing.append("关键地点设定")

    return {
        "complete": len(missing) == 0,
        "missing": missing,
        "called_tools": list(called_tools),
        "queried_characters": list(queried_characters),
    }


def _build_collected_data_summary(tool_call_history: list[dict], final_content: str) -> str:
    """从 Phase 1 的工具调用历史构建信息摘要，供 Phase 2 注入。"""
    if not tool_call_history:
        return "（未查询到额外信息）"

    categories: dict[str, list[dict]] = {}
    for call in tool_call_history:
        name = call.get("name", "")
        if name not in categories:
            categories[name] = []
        categories[name].append(call.get("arguments", {}))

    lines: list[str] = []
    label_map = {
        "query_character": "角色",
        "query_character_relations": "角色关系",
        "query_world_setting": "世界观",
        "query_location": "地点",
        "query_organization": "组织",
        "query_foreshadows": "伏笔",
        "query_item": "物品",
        "query_plot_timeline": "剧情时间线",
        "query_career": "职业体系",
        "list_available_entities": "实体总览",
    }

    for tool_name, calls in categories.items():
        label = label_map.get(tool_name, tool_name)
        if tool_name == "query_character":
            chars = [c.get("name", "?") for c in calls]
            lines.append(f"- {label}：{', '.join(chars)}（共{len(chars)}人）")
        elif tool_name == "query_world_setting":
            keywords = [c.get("keyword", "?") for c in calls]
            lines.append(f"- {label}：{', '.join(keywords)}")
        elif tool_name == "query_location":
            locs = [c.get("name", "?") for c in calls]
            lines.append(f"- {label}：{', '.join(locs)}")
        else:
            lines.append(f"- {label}：已查询（{len(calls)}次）")

    return "\n".join(lines) if lines else "（已查询信息）"


@router.get("/{project_id}/outlines/pending-entities")
async def get_pending_entities(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取大纲中引入但尚未入库的物品和地点。前端展示「需要补充」列表。"""
    await get_user_project(db, project_id, user)

    from app.models.item import Item
    from app.models.location import Location
    from app.models.outline import Outline

    outlines = (
        (await db.execute(
            select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number)
        ))
        .scalars().all()
    )

    # 收集大纲和展开章节中声明的所有新物品/地点
    from app.models.chapter import Chapter

    all_items: dict[str, dict] = {}
    all_locs: dict[str, dict] = {}

    # 1) 从大纲 structure 读取（1-1 模式）
    for o in outlines:
        raw = o.structure or {}
        for ni in raw.get("new_items") or []:
            if isinstance(ni, dict) and ni.get("name"):
                name = ni["name"].strip()
                if name and name not in all_items:
                    all_items[name] = {
                        "name": name, "category": ni.get("category", "杂物"),
                        "description": ni.get("description", "")[:200],
                        "from_chapter": o.chapter_number,
                    }
        for nl in raw.get("new_locations") or []:
            if isinstance(nl, dict) and nl.get("name"):
                name = nl["name"].strip()
                if name and name not in all_locs:
                    all_locs[name] = {
                        "name": name, "location_type": nl.get("location_type", "其他"),
                        "description": nl.get("description", "")[:200],
                        "from_chapter": o.chapter_number,
                    }

    # 2) 从展开章节的 expansion_plan 读取（1-N 模式）
    chapters = (
        (await db.execute(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
        ))
        .scalars().all()
    )
    for c in chapters:
        raw = c.expansion_plan or {}
        if not isinstance(raw, dict):
            continue
        for ni in raw.get("new_items") or []:
            if isinstance(ni, dict) and ni.get("name"):
                name = ni["name"].strip()
                if name and name not in all_items:
                    all_items[name] = {
                        "name": name, "category": ni.get("category", "杂物"),
                        "description": ni.get("description", "")[:200],
                        "from_chapter": c.chapter_number,
                    }
        for nl in raw.get("new_locations") or []:
            if isinstance(nl, dict) and nl.get("name"):
                name = nl["name"].strip()
                if name and name not in all_locs:
                    all_locs[name] = {
                        "name": name, "location_type": nl.get("location_type", "其他"),
                        "description": nl.get("description", "")[:200],
                        "from_chapter": c.chapter_number,
                    }

    # 检查 DB 中是否存在
    existing_items = {
        i.name for i in (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    }
    existing_locs = {
        l.name for l in (await db.execute(select(Location).where(Location.project_id == project_id))).scalars().all()
    }

    pending_items = [v for k, v in all_items.items() if k not in existing_items]
    pending_locs = [v for k, v in all_locs.items() if k not in existing_locs]

    return {
        "pending_items": pending_items,
        "pending_locations": pending_locs,
        "total": len(pending_items) + len(pending_locs),
    }


@router.post("/{project_id}/outlines/generate-pending-entities")
async def generate_pending_entities(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """用户确认后，生成 pending-entities 中缺失的物品和地点。"""
    await get_user_project(db, project_id, user)

    from app.models.chapter import Chapter
    from app.models.item import Item
    from app.models.location import Location
    from app.models.outline import Outline

    # 复用 pending-entities 的收集逻辑（大纲 + 展开章节）
    outlines = (
        (await db.execute(
            select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number)
        ))
        .scalars().all()
    )

    all_items: dict[str, dict] = {}
    all_locs: dict[str, dict] = {}
    for o in outlines:
        raw = o.structure or {}
        for ni in raw.get("new_items") or []:
            if isinstance(ni, dict) and ni.get("name"):
                name = ni["name"].strip()
                if name and name not in all_items:
                    all_items[name] = {"category": ni.get("category", "杂物"), "description": ni.get("description", "")[:200]}
        for nl in raw.get("new_locations") or []:
            if isinstance(nl, dict) and nl.get("name"):
                name = nl["name"].strip()
                if name and name not in all_locs:
                    all_locs[name] = {"location_type": nl.get("location_type", "其他"), "description": nl.get("description", "")[:200]}

    # 1-N 模式：从展开章节的 expansion_plan 读取
    chapters = (
        (await db.execute(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
        ))
        .scalars().all()
    )
    for c in chapters:
        raw = c.expansion_plan or {}
        if not isinstance(raw, dict):
            continue
        for ni in raw.get("new_items") or []:
            if isinstance(ni, dict) and ni.get("name"):
                name = ni["name"].strip()
                if name and name not in all_items:
                    all_items[name] = {"category": ni.get("category", "杂物"), "description": ni.get("description", "")[:200]}
        for nl in raw.get("new_locations") or []:
            if isinstance(nl, dict) and nl.get("name"):
                name = nl["name"].strip()
                if name and name not in all_locs:
                    all_locs[name] = {"location_type": nl.get("location_type", "其他"), "description": nl.get("description", "")[:200]}

    existing_items = {
        i.name for i in (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    }
    existing_locs = {
        l.name for l in (await db.execute(select(Location).where(Location.project_id == project_id))).scalars().all()
    }

    created = 0
    for name, info in all_items.items():
        if name in existing_items:
            continue
        db.add(Item(
            project_id=project_id, name=name, category=info["category"],
            rarity="普通", item_type="道具", description=info["description"],
            status="available",
        ))
        created += 1
    for name, info in all_locs.items():
        if name in existing_locs:
            continue
        db.add(Location(
            project_id=project_id, name=name, location_type=info["location_type"],
            description=info["description"], atmosphere="", danger_level="safe",
        ))
        created += 1

    if created:
        await db.commit()
        logger.warning(f"[outline] 用户补全: {len(all_items)} 物品 + {len(all_locs)} 地点 → 入库 {created}")

    return {"created": created, "items": len(all_items), "locations": len(all_locs)}


@router.post("/{project_id}/outlines/generate-async")
async def generate_outlines_async(
    project_id: int,
    req: OutlineGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步生成大纲：立即返回 task_id，后台执行。"""
    project = await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run_outline(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        await tracker.update(stage="preparing", message="准备生成大纲...")
        logger.info(f"[outline:{task_id}] preparing, entering session...")
        async with async_session() as task_db:
            logger.info(f"[outline:{task_id}] session ok, fetching project...")
            proj = await get_user_project(
                task_db, payload["project_id"], type("U", (), {"id": payload["user_id"]})()
            )

            # ======== 首次大纲生成：直接全量注入，跳过两阶段（角色少，无前文/伏笔可查）========
            existing_outlines = (
                await task_db.execute(
                    select(func.count(Outline.id)).where(
                        Outline.project_id == payload["project_id"]
                    )
                )
            ).scalar()
            is_first_outline = (existing_outlines or 0) == 0

            if is_first_outline:
                logger.info(
                    f"[outline:{task_id}] first outline, using full injection (no two-phase)"
                )
                ctx_full = await _project_context(
                    task_db, payload["project_id"], proj
                )  # 全量上下文
                engine, ai_client = await make_engine_and_client(task_db, payload["user_id"])
                await tracker.update(
                    stage="generating", message=f"AI 正在生成{payload['chapter_count']}章大纲..."
                )
                result = await engine.execute_skill(
                    "outline_create",
                    ai_client,
                    {
                        **ctx_full,
                        "title": proj.title,
                        "genre": proj.genre or "网文",
                        "theme": proj.genre or "网文",
                        "synopsis": proj.synopsis or "暂无简介",
                        "chapter_count": str(payload["chapter_count"]),
                        "narrative_perspective": proj.narrative_pov or "第三人称",
                        "narrative_pov": proj.narrative_pov or "第三人称",
                        "mcp_references": "",
                        "requirements": "",
                        "items_info": ctx_full.get("items_info", ""),
                        "locations_info": ctx_full.get("locations_info", ""),
                        "user_prompt": f"请为《{proj.title}》生成{payload['chapter_count']}章大纲。这是第一卷，没有前文大纲或伏笔需要参考。",
                    },
                )
                if result.get("error"):
                    await tracker.fail(result["error"])
                    return
                # 跳过 Phase 1 收集和 Phase 2 生成，直接进入保存
                await tracker.update(stage="saving", message="保存大纲...")
                outlines_data = result.get("json") or []
                if isinstance(outlines_data, list):
                    created_objs = []
                    for idx, item in enumerate(outlines_data):
                        o = _build_outline(
                            payload["project_id"],
                            item,
                            index=idx,
                            char_names=ctx_full["char_names"],
                            org_names=ctx_full["org_names"],
                        )
                        task_db.add(o)
                        created_objs.append(o)
                    await task_db.flush()
                    if (proj.outline_mode or "one_to_one") == "one_to_one":
                        for o in created_objs:
                            existing = (
                                (
                                    await task_db.execute(
                                        select(Chapter).where(
                                            Chapter.project_id == payload["project_id"],
                                            Chapter.chapter_number == o.chapter_number,
                                        )
                                    )
                                )
                                .scalars()
                                .first()
                            )
                            if existing:
                                continue
                            ch = Chapter(
                                project_id=payload["project_id"],
                                chapter_number=o.chapter_number,
                                title=o.title,
                                summary=o.summary[:200] if o.summary else "",
                                status="draft",
                                outline_id=None,
                                sub_index=1,
                                generation_mode="one_to_one",
                            )
                            task_db.add(ch)
                    await task_db.commit()
                await tracker.complete(message=f"大纲生成完成（{len(outlines_data)}章）")
                return

            # ======== 续写大纲：两阶段收集（有前文/伏笔可查）========
            logger.info(f"[outline:{task_id}] Phase 1: building skeleton context...")
            ctx_skeleton = await _project_context(
                task_db, payload["project_id"], proj, collect_only=True
            )
            logger.info(
                f"[outline:{task_id}] skeleton ok ({len(str(ctx_skeleton))} chars), creating engine..."
            )
            engine, ai_client = await make_engine_and_client(task_db, payload["user_id"])

            # Load Phase 1 collection prompt
            import os as _os

            _prompt_dir = _os.path.join(_os.path.dirname(__file__), "../../../skills/prompts")
            with open(_os.path.join(_prompt_dir, "outline_collect.md")) as _f:
                collection_system_prompt = _f.read()

            # Build Phase 1 messages: minimal context + strict collection instruction
            phase1_messages = [
                {"role": "system", "content": collection_system_prompt},
            ]
            # Inject only skeleton info (no full profiles, no detailed world settings)
            _novel_info = f"【小说信息】\n书名：{proj.title}\n题材：{proj.genre or '网文'}\n简介：{proj.synopsis or '暂无简介'}\n叙事视角：{proj.narrative_pov or '第三人称'}\n章节数：{payload['chapter_count']}"
            phase1_messages.append({"role": "system", "content": _novel_info})
            if ctx_skeleton.get("world_info"):
                phase1_messages.append(
                    {"role": "system", "content": "【世界观概要】\n" + ctx_skeleton["world_info"]}
                )
            if ctx_skeleton.get("characters_info"):
                phase1_messages.append(
                    {
                        "role": "system",
                        "content": "【角色骨架】\n"
                        + ctx_skeleton["characters_info"]
                        + "\n\n💡 以上仅角色骨架（姓名+身份）。性格、背景、能力、动机、弱点等详细信息需通过 query_character 工具查询。",
                    }
                )
            if ctx_skeleton.get("organizations_info"):
                phase1_messages.append(
                    {
                        "role": "system",
                        "content": "【组织列表】\n" + ctx_skeleton["organizations_info"],
                    }
                )
            phase1_messages.append(
                {
                    "role": "user",
                    "content": f"请为《{proj.title}》收集生成{payload['chapter_count']}章大纲所需的信息。",
                }
            )

            tools = get_chapter_tools()
            tool_executor = make_tool_executor(
                task_db, payload["project_id"], payload["chapter_count"] + 1
            )

            await tracker.update(stage="collecting", message="AI 正在查询角色和世界观信息...")
            logger.info(f"[outline:{task_id}] Phase 1: calling AI for collection...")

            MAX_COLLECTION_RETRIES = 2
            collection_result = None
            for attempt in range(MAX_COLLECTION_RETRIES + 1):
                collection_result = await ai_client.chat_with_tools(
                    messages=phase1_messages,
                    tools=tools,
                    tool_executor=tool_executor,
                )
                if collection_result.get("error"):
                    await tracker.fail(collection_result["error"])
                    return

                content = collection_result.get("content", "")
                tool_history = collection_result.get("tool_call_history", [])

                # Check trigger phrase
                if "信息收集完毕" not in content:
                    logger.warning(
                        f"[outline:{task_id}] Phase 1 attempt {attempt + 1}: no trigger phrase, forcing retry"
                    )
                    phase1_messages.append({"role": "assistant", "content": content[:500]})
                    phase1_messages.append(
                        {
                            "role": "user",
                            "content": "请确认信息是否收集完毕。如已完毕，输出「信息收集完毕，请求进入生成阶段。」",
                        }
                    )
                    continue

                # Validate completeness
                validation = _validate_collection(tool_history, ctx_skeleton)
                logger.info(
                    f"[outline:{task_id}] Phase 1 validation: complete={validation['complete']}, missing={validation['missing']}, tools={validation['called_tools']}"
                )
                if validation["complete"]:
                    break

                if attempt < MAX_COLLECTION_RETRIES:
                    missing_str = "、".join(validation["missing"])
                    logger.info(
                        f"[outline:{task_id}] Phase 1: missing {missing_str}, retrying ({attempt + 1}/{MAX_COLLECTION_RETRIES})"
                    )
                    phase1_messages.append({"role": "assistant", "content": content[:500]})
                    phase1_messages.append(
                        {
                            "role": "user",
                            "content": f"以下信息尚未收集：{missing_str}。请继续补充查询这些内容。",
                        }
                    )
                else:
                    logger.warning(
                        f"[outline:{task_id}] Phase 1: still missing {validation['missing']} after {MAX_COLLECTION_RETRIES} retries, proceeding anyway"
                    )
                    break

            # ======== Phase 2: Outline Generation ========
            logger.info(f"[outline:{task_id}] Phase 2: building full context...")
            ctx_full = await _project_context(task_db, payload["project_id"], proj)  # Full context
            logger.info(f"[outline:{task_id}] full context ok ({len(str(ctx_full))} chars)")

            collected_summary = _build_collected_data_summary(
                collection_result.get("tool_call_history", []),
                collection_result.get("content", ""),
            )
            logger.info(f"[outline:{task_id}] collected summary: {collected_summary[:200]}...")

            await tracker.update(
                stage="generating", message=f"AI 正在生成{payload['chapter_count']}章大纲..."
            )
            logger.info(f"[outline:{task_id}] Phase 2: calling AI for generation (no tools)...")
            result = await engine.execute_skill(
                "outline_create",
                ai_client,
                {
                    **ctx_full,
                    "title": proj.title,
                    "genre": proj.genre or "网文",
                    "theme": proj.genre or "网文",
                    "synopsis": proj.synopsis or "暂无简介",
                    "chapter_count": str(payload["chapter_count"]),
                    "narrative_perspective": proj.narrative_pov or "第三人称",
                    "narrative_pov": proj.narrative_pov or "第三人称",
                    "mcp_references": "",
                    "requirements": "",
                    "user_prompt": f"请为《{proj.title}》生成{payload['chapter_count']}章大纲。\n\n【你已查询到的信息概要】\n{collected_summary}\n\n请基于以上信息生成大纲。",
                    "_collected_data": collected_summary,
                },
                tools=None,
                tool_executor=None,
            )  # Phase 2: no tools

            if result.get("error"):
                await tracker.fail(result["error"])
                return

            await tracker.update(stage="saving", message="保存大纲...")
            outlines_data = result.get("json") or []
            if isinstance(outlines_data, list):
                created_objs = []
                for idx, item in enumerate(outlines_data):
                    o = _build_outline(
                        payload["project_id"],
                        item,
                        index=idx,
                        char_names=ctx_full["char_names"],
                        org_names=ctx_full["org_names"],
                    )
                    task_db.add(o)
                    created_objs.append(o)
                await task_db.flush()
                if (proj.outline_mode or "one_to_one") == "one_to_one":
                    for o in created_objs:
                        existing = (
                            (
                                await task_db.execute(
                                    select(Chapter).where(
                                        Chapter.project_id == payload["project_id"],
                                        Chapter.chapter_number == o.chapter_number,
                                    )
                                )
                            )
                            .scalars()
                            .first()
                        )
                        if existing:
                            continue
                        ch = Chapter(
                            project_id=payload["project_id"],
                            chapter_number=o.chapter_number,
                            title=o.title,
                            summary=o.summary[:200] if o.summary else "",
                            status="draft",
                            outline_id=None,
                            sub_index=1,
                            generation_mode="one_to_one",
                        )
                        task_db.add(ch)
                await task_db.commit()
            await tracker.complete(message=f"大纲生成完成（{len(outlines_data)}章）")

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="outline_new",
        title="生成大纲",
        payload={"chapter_count": req.chapter_count, "project_id": project_id, "user_id": user.id},
        runner=_run_outline,
    )
    return {"task_id": task_id}


@router.get("/{project_id}/outlines")
async def list_outlines(
    project_id: int,
    limit: int = 0,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    from sqlalchemy import func

    await get_user_project(db, project_id, user)  # 权限校验

    # 总数
    total = (
        await db.execute(
            select(func.count(Outline.id)).where(Outline.project_id == project_id)
        )
    ).scalar() or 0

    query = (
        select(Outline)
        .where(Outline.project_id == project_id)
        .order_by(Outline.chapter_number)
    )
    if limit > 0:
        query = query.offset(offset).limit(limit)

    outlines = (await db.execute(query)).scalars().all()

    # 预查每个大纲关联的章节数
    chapter_counts = {}
    if outlines:
        rows = (
            await db.execute(
                select(Chapter.outline_id, func.count(Chapter.id))
                .where(Chapter.project_id == project_id, Chapter.outline_id.isnot(None))
                .group_by(Chapter.outline_id)
            )
        ).all()
        chapter_counts = {r[0]: r[1] for r in rows}

    items = [
        {
            "id": o.id,
            "chapter_number": o.chapter_number,
            "title": o.title,
            "summary": o.summary,
            "scenes": o.scenes,
            "characters": o.characters,
            "key_points": o.key_points,
            "emotion": o.emotion,
            "goal": o.goal,
            "structure": o.structure or {},
            "has_chapters": chapter_counts.get(o.id, 0) > 0,
            "chapter_count": chapter_counts.get(o.id, 0),
        }
        for o in outlines
    ]

    # 分页模式：返回 total + items；兼容模式：返回纯数组
    if limit > 0:
        return {"total": total, "limit": limit, "offset": offset, "items": items}
    return items


@router.post("/{project_id}/outlines")
async def create_outline(
    project_id: int,
    req: OutlineCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    o = Outline(project_id=project_id, **req.model_dump())
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return {"id": o.id}


@router.put("/{project_id}/outlines/{outline_id}")
async def update_outline(
    project_id: int,
    outline_id: int,
    req: OutlineCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    o = (
        await db.execute(
            select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "大纲不存在")
    for key, value in req.model_dump().items():
        setattr(o, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/outlines/{outline_id}")
async def delete_outline(
    project_id: int,
    outline_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    o = (
        await db.execute(
            select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "大纲不存在")
    # 级联删除该大纲展开的所有章节（1→N 模式）及其关联数据
    from app.services.chapter_service import ChapterService

    chapters = (
        (
            await db.execute(
                select(Chapter).where(
                    Chapter.outline_id == outline_id, Chapter.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    deleted_words = sum(c.word_count or 0 for c in chapters)
    chapter_count = len(chapters)
    if chapters:
        # 1→1 模式下可能有章节的 chapter_number 和大纲相同但 outline_id 为空，也一起清理
        chapter_service = ChapterService(db, project_id, user.id)
        await chapter_service.cleanup_chapters_data([c.id for c in chapters])
        for c in chapters:
            await db.delete(c)
        # 回收项目字数
        if deleted_words > 0:
            proj = await get_user_project(db, project_id, user)
            proj.current_word_count = max(0, (proj.current_word_count or 0) - deleted_words)
    await db.delete(o)
    await db.commit()
    return {"ok": True, "deleted_chapters": chapter_count, "deleted_words": deleted_words}


@router.post("/{project_id}/outlines/continue")
async def continue_outlines(
    project_id: int,
    req: OutlineContinueRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """大纲续写：在现有大纲基础上继续生成。

    上下文优化：
    - 最近 N 章大纲传完整版（title + summary + key_points）
    - 更早的大纲传精简版（chapter_number + title + summary）
    - 超过 30 条时进一步压缩为每 5 章一条摘要
    """
    from app.core.config import settings

    proj = await get_user_project(db, project_id, user)
    outlines = (
        (
            await db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    chapters = (
        (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    foreshadows_list = (
        (
            await db.execute(
                select(Foreshadow).where(
                    Foreshadow.project_id == project_id,
                    Foreshadow.status.in_(["pending", "planted"]),
                )
            )
        )
        .scalars()
        .all()
    )
    ctx = await _project_context(db, project_id, proj, use_tools=True)

    # ===== 大纲上下文截断优化 =====
    full_limit = settings.OUTLINE_CONTEXT_CHAPTERS  # 默认 20
    if len(outlines) <= full_limit:
        # 章节数不多，全部传完整版
        recent_outlines_json = json.dumps(
            [
                {
                    "chapter_number": o.chapter_number,
                    "title": o.title,
                    "summary": o.summary,
                    "key_points": o.key_points,
                }
                for o in outlines
            ],
            ensure_ascii=False,
        )
    else:
        # 最近 N 章：完整版
        recent = outlines[-full_limit:]
        older = outlines[:-full_limit]
        # 更早的章节：精简版（去掉 key_points/scenes）
        older_brief = [
            {
                "chapter_number": o.chapter_number,
                "title": o.title,
                "summary": (o.summary or "")[:200],
            }
            for o in older
        ]
        # 如果精简后仍然超过 30 条，进一步压缩为每 5 章一条
        if len(older_brief) > 30:
            compressed = []
            for i in range(0, len(older_brief), 5):
                chunk = older_brief[i : i + 5]
                first, last = chunk[0], chunk[-1]
                summaries = "；".join(c["summary"][:30] for c in chunk if c["summary"])
                compressed.append(
                    {
                        "chapter_number": f"{first['chapter_number']}-{last['chapter_number']}",
                        "title": f"第{first['chapter_number']}-{last['chapter_number']}章概要",
                        "summary": summaries[:200],
                    }
                )
            older_brief = compressed
        # 合并：精简版 + 完整版
        recent_outlines_json = json.dumps(
            older_brief
            + [
                {
                    "chapter_number": o.chapter_number,
                    "title": o.title,
                    "summary": o.summary,
                    "key_points": o.key_points,
                }
                for o in recent
            ],
            ensure_ascii=False,
        )

    existing_chapters = (
        json.dumps(
            [
                {"chapter_number": c.chapter_number, "title": c.title, "summary": c.summary or ""}
                for c in chapters
            ],
            ensure_ascii=False,
        )
        if chapters
        else "暂无"
    )

    current_count = max((o.chapter_number for o in outlines), default=0)
    start_chapter, end_chapter = current_count + 1, current_count + req.chapter_count

    foreshadow_context = _format_foreshadows_for_outline(
        foreshadows_list, start_chapter, end_chapter
    )

    # 叙事视角：前端留空 = 按小说设定（取项目默认）
    effective_pov = req.narrative_pov or proj.narrative_pov or "第三人称"

    engine, ai_client = await make_engine_and_client(
        db, user.id, model_override=(req.ai_model or None)
    )
    # 拼装用户额外要求（故事方向/情节阶段/其他要求）
    extra_req_parts = []
    if req.story_direction:
        extra_req_parts.append(f"故事发展方向：{req.story_direction}")
    if req.plot_stage:
        extra_req_parts.append(f"当前情节阶段：{req.plot_stage}")
    if req.other_requirements:
        extra_req_parts.append(f"其他要求：{req.other_requirements}")
    extra_req_text = ("\n".join(extra_req_parts) + "\n") if extra_req_parts else ""

    result = await engine.execute_skill(
        "outline_continue",
        ai_client,
        {
            **ctx,
            "title": proj.title,
            "genre": proj.genre or "网文",
            "theme": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "chapter_count": str(req.chapter_count),
            "current_chapter_count": str(current_count),
            "start_chapter": str(start_chapter),
            "end_chapter": str(end_chapter),
            "total_planned_chapters": str(current_count + req.chapter_count),
            "recent_outlines": recent_outlines_json,
            "existing_chapters": existing_chapters,
            "foreshadow_context": foreshadow_context,
            "foreshadow_reminders": foreshadow_context,
            "narrative_pov": effective_pov,
            "narrative_perspective": effective_pov,
            "plot_stage_instruction": req.plot_stage or "",
            "story_direction": req.story_direction or "",
            "requirements": req.other_requirements or "",
            "mcp_references": "",
            "user_prompt": f"请在已有大纲（共{current_count}章）基础上，续写第{start_chapter}到{end_chapter}章的大纲。如需查询前几章、角色关系、伏笔状态等，可使用工具。\n{extra_req_text}",
        },
        tools=get_chapter_tools(),
        tool_executor=make_tool_executor(db, project_id, start_chapter),
    )
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    created_objs = []
    for item in outlines_data:
        o = _build_outline(
            project_id, item, char_names=ctx["char_names"], org_names=ctx["org_names"]
        )
        db.add(o)
        created_objs.append(o)
        created.append(item)
    await db.flush()

    # 1对1模式：自动为续写的大纲创建对应章节
    if (proj.outline_mode or "one_to_one") == "one_to_one":
        for o in created_objs:
            existing = (
                (
                    await db.execute(
                        select(Chapter).where(
                            Chapter.project_id == project_id,
                            Chapter.chapter_number == o.chapter_number,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing:
                continue
            ch = Chapter(
                project_id=project_id,
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

    # ===== 新角色检测 =====
    # 从新生成的大纲中提取角色名，与已有角色对比，找出未注册的角色
    existing_chars = {
        c.name
        for c in (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    }
    existing_org_names = {
        o.name
        for o in (
            await db.execute(select(Organization).where(Organization.project_id == project_id))
        )
        .scalars()
        .all()
    }
    new_characters = set()
    for item in outlines_data:
        chars = item.get("characters", [])
        if not isinstance(chars, list):
            continue
        for ch in chars:
            if isinstance(ch, dict):
                name = ch.get("name", "")
                ctype = ch.get("type", "character")
            elif isinstance(ch, str):
                name = ch
                ctype = "character"
            else:
                continue
            # 只关注角色，跳过组织
            if ctype == "organization":
                continue
            if name in existing_org_names:
                continue
            if name and name not in existing_chars:
                new_characters.add(name)

    response = {"outlines": created, "count": len(created)}
    if new_characters:
        response["new_characters"] = list(new_characters)

    # 验证大纲中涉及的角色/组织是否都已创建
    world_ctx = _build_world_context_for_validate(proj)
    asyncio.create_task(
        validate_outline_entities(
            db, project_id, proj.title, proj.genre or "网文", world_ctx, ai_client
        )
    )

    return response


@router.post("/{project_id}/outlines/continue-async")
async def continue_outlines_async(
    project_id: int,
    req: OutlineContinueRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步续写大纲：立即返回 task_id，后台执行。"""
    await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run_continue(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        await tracker.update(stage="preparing", message="准备续写大纲...")
        # 复用同步逻辑（在独立 session 中）
        async with async_session() as task_db:
            # 构造一个 mock request 对象
            class MockReq:
                chapter_count = payload["chapter_count"]

            # 调用核心逻辑（提取为共享函数会更优雅，但这里直接复用）
            proj = await get_user_project(
                task_db, payload["project_id"], type("U", (), {"id": payload["user_id"]})()
            )
            outlines = (
                (
                    await task_db.execute(
                        select(Outline)
                        .where(Outline.project_id == payload["project_id"])
                        .order_by(Outline.chapter_number)
                    )
                )
                .scalars()
                .all()
            )
            current_count = max((o.chapter_number for o in outlines), default=0)
            await tracker.update(
                stage="generating",
                message=f"AI 续写第{current_count + 1}到{current_count + payload['chapter_count']}章...",
            )
            # 调用同步版本的核心逻辑
            # 直接调用路由函数太复杂，这里内联核心逻辑
            ctx = await _project_context(task_db, payload["project_id"], proj)
            from app.core.config import settings

            full_limit = settings.OUTLINE_CONTEXT_CHAPTERS
            if len(outlines) <= full_limit:
                recent_outlines_json = json.dumps(
                    [
                        {
                            "chapter_number": o.chapter_number,
                            "title": o.title,
                            "summary": o.summary,
                            "key_points": o.key_points,
                        }
                        for o in outlines
                    ],
                    ensure_ascii=False,
                )
            else:
                recent = outlines[-full_limit:]
                older = outlines[:-full_limit]
                older_brief = [
                    {
                        "chapter_number": o.chapter_number,
                        "title": o.title,
                        "summary": (o.summary or "")[:200],
                    }
                    for o in older
                ]
                if len(older_brief) > 30:
                    compressed = []
                    for i in range(0, len(older_brief), 5):
                        chunk = older_brief[i : i + 5]
                        first, last = chunk[0], chunk[-1]
                        summaries = "；".join(c["summary"][:30] for c in chunk if c["summary"])
                        compressed.append(
                            {
                                "chapter_number": f"{first['chapter_number']}-{last['chapter_number']}",
                                "title": f"第{first['chapter_number']}-{last['chapter_number']}章概要",
                                "summary": summaries[:200],
                            }
                        )
                    older_brief = compressed
                recent_outlines_json = json.dumps(
                    older_brief
                    + [
                        {
                            "chapter_number": o.chapter_number,
                            "title": o.title,
                            "summary": o.summary,
                            "key_points": o.key_points,
                        }
                        for o in recent
                    ],
                    ensure_ascii=False,
                )
            chapters = (
                (
                    await task_db.execute(
                        select(Chapter)
                        .where(Chapter.project_id == payload["project_id"])
                        .order_by(Chapter.chapter_number)
                    )
                )
                .scalars()
                .all()
            )
            existing_chapters = (
                json.dumps(
                    [
                        {
                            "chapter_number": c.chapter_number,
                            "title": c.title,
                            "summary": c.summary or "",
                        }
                        for c in chapters
                    ],
                    ensure_ascii=False,
                )
                if chapters
                else "暂无"
            )
            foreshadows_list = (
                (
                    await task_db.execute(
                        select(Foreshadow).where(
                            Foreshadow.project_id == payload["project_id"],
                            Foreshadow.status.in_(["pending", "planted"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
            start_chapter, end_chapter = current_count + 1, current_count + payload["chapter_count"]
            foreshadow_context = _format_foreshadows_for_outline(
                foreshadows_list, start_chapter, end_chapter
            )
            # 叙事视角：前端留空 = 按小说设定
            effective_pov = payload.get("narrative_pov") or proj.narrative_pov or "第三人称"
            engine, ai_client = await make_engine_and_client(
                task_db, payload["user_id"], model_override=(payload.get("ai_model") or None)
            )
            # 拼装用户额外要求
            extra_req_parts = []
            if payload.get("story_direction"):
                extra_req_parts.append(f"故事发展方向：{payload['story_direction']}")
            if payload.get("plot_stage"):
                extra_req_parts.append(f"当前情节阶段：{payload['plot_stage']}")
            if payload.get("other_requirements"):
                extra_req_parts.append(f"其他要求：{payload['other_requirements']}")
            extra_req_text = ("\n".join(extra_req_parts) + "\n") if extra_req_parts else ""
            result = await engine.execute_skill(
                "outline_continue",
                ai_client,
                {
                    **ctx,
                    "title": proj.title,
                    "genre": proj.genre or "网文",
                    "theme": proj.genre or "网文",
                    "synopsis": proj.synopsis or "暂无简介",
                    "chapter_count": str(payload["chapter_count"]),
                    "current_chapter_count": str(current_count),
                    "start_chapter": str(start_chapter),
                    "end_chapter": str(end_chapter),
                    "total_planned_chapters": str(current_count + payload["chapter_count"]),
                    "recent_outlines": recent_outlines_json,
                    "existing_chapters": existing_chapters,
                    "foreshadow_context": foreshadow_context,
                    "foreshadow_reminders": foreshadow_context,
                    "narrative_pov": effective_pov,
                    "narrative_perspective": effective_pov,
                    "plot_stage_instruction": payload.get("plot_stage") or "",
                    "story_direction": payload.get("story_direction") or "",
                    "requirements": payload.get("other_requirements") or "",
                    "mcp_references": "",
                    "user_prompt": f"请在已有大纲（共{current_count}章）基础上，续写第{start_chapter}到{end_chapter}章的大纲。如需查询前几章、角色关系、伏笔状态等，可使用工具。\n{extra_req_text}",
                },
                tools=get_chapter_tools(),
                tool_executor=make_tool_executor(task_db, payload["project_id"], start_chapter),
            )
            if result.get("error"):
                await tracker.fail(result["error"])
                return
            await tracker.update(stage="saving", message="保存大纲...")
            outlines_data = result.get("json") or []
            if isinstance(outlines_data, list):
                created_objs = []
                for item in outlines_data:
                    o = _build_outline(
                        payload["project_id"],
                        item,
                        char_names=ctx["char_names"],
                        org_names=ctx["org_names"],
                    )
                    task_db.add(o)
                    created_objs.append(o)
                await task_db.flush()
                # 1对1模式：自动为续写的大纲创建对应章节
                if (proj.outline_mode or "one_to_one") == "one_to_one":
                    for o in created_objs:
                        existing = (
                            (
                                await task_db.execute(
                                    select(Chapter).where(
                                        Chapter.project_id == payload["project_id"],
                                        Chapter.chapter_number == o.chapter_number,
                                    )
                                )
                            )
                            .scalars()
                            .first()
                        )
                        if existing:
                            continue
                        ch = Chapter(
                            project_id=payload["project_id"],
                            chapter_number=o.chapter_number,
                            title=o.title,
                            summary=o.summary[:200] if o.summary else "",
                            status="draft",
                            outline_id=None,
                            sub_index=1,
                            generation_mode="one_to_one",
                        )
                        task_db.add(ch)
                await task_db.commit()
            await tracker.complete(message=f"续写完成（{len(outlines_data)}章）")

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="outline_continue",
        title="续写大纲",
        payload={
            "chapter_count": req.chapter_count,
            "project_id": project_id,
            "user_id": user.id,
            "story_direction": req.story_direction,
            "plot_stage": req.plot_stage,
            "narrative_pov": req.narrative_pov,
            "other_requirements": req.other_requirements,
            "ai_model": req.ai_model,
        },
        runner=_run_continue,
    )
    return {"task_id": task_id}


async def _expand_outline_core(
    db: AsyncSession,
    project_id: int,
    outline_id: int,
    target_chapter_count: int,
    user_id: int,
    skip_existing_check: bool = False,
    replace_existing: bool = False,
    append_existing: bool = False,
    strategy: str = "balanced",
) -> dict:
    """大纲展开为多章的核心逻辑（同步/异步/批量复用）。

    AI 将一条大纲拆成 N 个章节计划，创建 N 个 Chapter（关联 outline_id，
    含 sub_index + expansion_plan）。

    三种模式：
    - 默认（new）：首次展开，已展开则报错
    - replace_existing=True：覆盖模式，先删旧章节，新章节从旧起始号开始
    - append_existing=True：追加模式，保留旧章节，新章节接在后面（sub_index 续接），
      并把已有规划喂给 AI 做差异化（避免重复）

    Args:
        db: 数据库会话
        project_id: 项目ID
        outline_id: 大纲ID
        target_chapter_count: 目标章节数
        user_id: 用户ID（用于构建 AI 客户端）
        skip_existing_check: 跳过"已展开"检查（批量模式下由调用方统一校验）
        replace_existing: True 时先删除该大纲已展开的旧章节再重新展开（覆盖模式）
        append_existing: True 时保留旧章节，在后面追加新章节（追加模式）
        strategy: 展开策略 balanced/climax/detail（默认 balanced）

    Returns:
        {"expanded": [...], "count": int, "start_chapter": int, "replaced": int, "appended": bool}

    Raises:
        HTTPException: 大纲不存在 / 已展开 / AI 返回格式错误
    """
    proj = await get_user_project(db, project_id, type("U", (), {"id": user_id})())
    outline = (
        await db.execute(
            select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not outline:
        raise HTTPException(404, "大纲不存在")

    replaced_count = 0
    old_start_chapter = None
    append_base_sub_index = 0  # 追加模式：新章节 sub_index 从此值+1 开始
    if replace_existing:
        # 覆盖模式：先删除该大纲已展开的旧章节，新章节从旧起始号开始（保证章号连续，不留空洞）
        old_chapters = (
            (
                await db.execute(
                    select(Chapter)
                    .where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
                    .order_by(Chapter.chapter_number)
                )
            )
            .scalars()
            .all()
        )
        if old_chapters:
            old_start_chapter = old_chapters[0].chapter_number  # 删除前记下起始号
            deleted_words = sum(c.word_count or 0 for c in old_chapters)
            # 先清理关联的 PlotAnalysis / StoryMemory / 向量 / 分析伏笔 / GenerationHistory
            chapter_service = ChapterService(db, project_id, user_id=user_id)
            await chapter_service.cleanup_chapters_data([c.id for c in old_chapters])
            # 再删除章节本身
            for c in old_chapters:
                await db.delete(c)
            await db.flush()
            replaced_count = len(old_chapters)
            # 回收项目字数
            if deleted_words > 0:
                proj.current_word_count = max(0, (proj.current_word_count or 0) - deleted_words)
            logger.info(
                f"[expand] 覆盖模式：删除大纲 {outline_id} 的旧 {replaced_count} 章（{deleted_words}字），新章节将从第{old_start_chapter}章开始"
            )
    elif append_existing:
        # 追加模式：读取已有章节，记下最大 sub_index 供新章节续接，并拼成上下文喂给 AI
        existing = (
            (
                await db.execute(
                    select(Chapter)
                    .where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
                    .order_by(Chapter.sub_index)
                )
            )
            .scalars()
            .all()
        )
        if existing:
            append_base_sub_index = max(c.sub_index or 0 for c in existing)
            logger.info(
                f"[expand] 追加模式：大纲 {outline_id} 已有 {len(existing)} 章（sub_index 最大 {append_base_sub_index}），将追加 {target_chapter_count} 章"
            )
    elif not skip_existing_check:
        existing_chapters = (
            (
                await db.execute(
                    select(Chapter).where(
                        Chapter.outline_id == outline_id, Chapter.project_id == project_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if existing_chapters:
            raise HTTPException(
                400, f"此大纲已展开为 {len(existing_chapters)} 章，请先删除再重新展开"
            )

    # 追加模式：把已有规划摘要拼进 user_prompt，让 AI 做差异化续写
    existing_context = ""
    if append_existing and append_base_sub_index > 0:
        existing_list = (
            (
                await db.execute(
                    select(Chapter)
                    .where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
                    .order_by(Chapter.sub_index)
                )
            )
            .scalars()
            .all()
        )
        parts = []
        for c in existing_list:
            plan = c.expansion_plan if isinstance(c.expansion_plan, dict) else {}
            summary = (
                (plan.get("plot_summary") if isinstance(plan, dict) else "") or c.summary or ""
            )
            events = plan.get("key_events") if isinstance(plan, dict) else []
            events_str = "、".join(events[:3]) if events else ""
            line = f"  第{c.sub_index}节《{c.title}》：{summary[:120]}"
            if events_str:
                line += f"（关键事件：{events_str}）"
            parts.append(line)
        existing_context = (
            f"\n\n【🔴 已有章节（必须延续，不得重复）】\n该大纲此前已展开 {len(existing_list)} 节：\n"
            + "\n".join(parts)
            + f"\n\n请在此基础上【继续追加】{target_chapter_count} 节，sub_index 从 {append_base_sub_index + 1} 开始。"
            "新章节必须承接已有内容的剧情走向，不得与上述关键事件重复。"
        )

    ctx = await _project_context(db, project_id, proj, use_tools=True)

    # ===== 构建完整的 outline_content（卷概览）=====
    outline_parts = []
    if outline.summary:
        outline_parts.append(f"【卷概要】{outline.summary}")
    if outline.goal:
        outline_parts.append(f"【叙事目标】{outline.goal}")
    if outline.emotion:
        outline_parts.append(f"【情绪基调】{outline.emotion}")
    if outline.key_points:
        kp_lines = "\n".join(f"  - {kp}" for kp in outline.key_points)
        outline_parts.append(f"【关键情节点】\n{kp_lines}")
    if outline.scenes:
        scene_lines = []
        for sc in outline.scenes:
            if isinstance(sc, dict):
                st = sc.get("scene_title", "")
                sd = sc.get("scene_desc", "")[:100]
                se = sc.get("emotion", "")
                scene_lines.append(f"  - {st}（{se}）：{sd}")
            elif isinstance(sc, str):
                scene_lines.append(f"  - {sc}")
        if scene_lines:
            outline_parts.append("【场景设定】\n" + "\n".join(scene_lines))
    if outline.characters:
        chars_str = "、".join(str(c) for c in outline.characters)
        outline_parts.append(f"【涉及角色】{chars_str}")
    # structure 中的深度设计字段（shuang_design / character_intents 等）
    if isinstance(outline.structure, dict) and outline.structure:
        struct_parts = []
        if outline.structure.get("shuang_design"):
            sd = outline.structure["shuang_design"]
            if isinstance(sd, dict):
                struct_parts.append(f"  爽点设计：{sd}")
            elif isinstance(sd, str):
                struct_parts.append(f"  爽点设计：{sd}")
        if outline.structure.get("character_intents"):
            ci = outline.structure["character_intents"]
            if isinstance(ci, list):
                ci_lines = []
                for item in ci:
                    if isinstance(item, dict):
                        ci_lines.append(
                            f"    {item.get('character', '?')}：本章目标={item.get('this_chapter_goal', '?')}，当前欲求={item.get('immediate_want', '?')}"
                        )
                if ci_lines:
                    struct_parts.append("  角色微意图：\n" + "\n".join(ci_lines))
            elif isinstance(ci, str):
                struct_parts.append(f"  角色微意图：{ci}")
        if outline.structure.get("reader_hook"):
            struct_parts.append(f"  读者钩子：{outline.structure['reader_hook']}")
        if outline.structure.get("scene_anchor"):
            struct_parts.append(f"  场景锚点：{outline.structure['scene_anchor']}")
        if struct_parts:
            outline_parts.append("【深度设计】\n" + "\n".join(struct_parts))
    outline_content = "\n\n".join(outline_parts) if outline_parts else (outline.summary or "")

    # ===== 构建 context_info（相邻大纲）=====
    context_lines = []
    # 前一个大纲
    if outline.chapter_number > 1:
        prev_outline = (
            await db.execute(
                select(Outline).where(
                    Outline.project_id == project_id,
                    Outline.chapter_number == outline.chapter_number - 1,
                )
            )
        ).scalar_one_or_none()
        if prev_outline:
            context_lines.append(
                f"← 前一卷（第{prev_outline.chapter_number}卷）《{prev_outline.title}》：{prev_outline.summary[:150] or '暂无概要'}"
            )
    # 后两个大纲
    next_outlines = (
        (
            await db.execute(
                select(Outline)
                .where(
                    Outline.project_id == project_id,
                    Outline.chapter_number > outline.chapter_number,
                )
                .order_by(Outline.chapter_number)
                .limit(2)
            )
        )
        .scalars()
        .all()
    )
    for no in next_outlines:
        context_lines.append(
            f"→ 后卷（第{no.chapter_number}卷）《{no.title}》：{no.summary[:150] or '暂无概要'}"
        )
    context_info = "\n".join(context_lines) if context_lines else "（无相邻大纲信息）"

    engine, ai_client = await make_engine_and_client(db, user_id)

    # ===== 构建模板变量（数据计算，不含指令文字——指令在 md 模板中）=====
    key_points = outline.key_points or []
    focus_kps = [kp for kp in key_points if "【重点】" in str(kp)]
    general_kps = [kp for kp in key_points if "【一般】" in str(kp)]
    weak_kps = [kp for kp in key_points if "【弱】" in str(kp)]
    kp_count = len(focus_kps)

    # 重点情节点文本
    if focus_kps:
        focus_kps_text = "\n".join(f"  · {kp}" for kp in focus_kps)
    else:
        focus_kps_text = "（本卷未标注【重点】情节点）"

    # 分配规则
    if focus_kps:
        if target_chapter_count >= kp_count:
            kp_allocation_rule = f"共{kp_count}个【重点】，{target_chapter_count}个子章节。前{kp_count}个子章节各承担1个【重点】的推进，第{target_chapter_count}个子章节收束所有线索并引爆本卷小高潮。"
        else:
            # 重点多于子章节：前 N-1 章每章1个，最后一章承担剩余
            overflow = kp_count - (target_chapter_count - 1)
            kp_allocation_rule = (
                f"共{kp_count}个【重点】，仅{target_chapter_count}个子章节。"
                f"前{target_chapter_count - 1}个子章节各承担1个【重点】，"
                f"第{target_chapter_count}个子章节承担剩余{overflow}个【重点】并收束全卷。"
            )
    else:
        kp_allocation_rule = (
            f"将卷概览中的核心剧情按自然节奏分配到{target_chapter_count}个子章节中。"
        )

    # 无重点时的兜底
    no_focus_fallback = ""
    if not focus_kps:
        no_focus_fallback = (
            "第1章必须让主角进入核心场景并开始实质性行动，不允许全章仅做环境铺陈或角色出场。"
        )

    # 【一般】/【弱】规则
    general_kps_rule = (
        f"【一般】情节点（{len(general_kps)}个）作为子章节的辅助内容，不可喧宾夺主取代【重点】。"
        if general_kps
        else ""
    )
    weak_kps_rule = f"【弱】情节点（{len(weak_kps)}个）字数不够时可省略。" if weak_kps else ""

    # 上下文提示（供模板 <task> 使用）
    context_note = ""
    if context_lines:
        context_note = "同时参考「上下文参考」中相邻卷的内容——前一卷的结尾和后续卷的起点，确保子章节能自然衔接前后卷。"

    # 模式叠加（climax/detail）
    mode_extra = ""
    mode_extras = {
        "climax": "【高潮模式叠加】将最激烈的对抗集中到最后两个子章节，前几章蓄势。",
        "detail": "【细节模式叠加】每个情节点允许更多心理描写和对话展开，但不得延缓【重点】的推进节奏。",
    }
    if strategy in mode_extras:
        mode_extra = mode_extras[strategy]

    # 角色意图继承指引
    structure = outline.structure if isinstance(outline.structure, dict) else {}
    if structure.get("character_intents"):
        char_intent_guidance = (
            "每个子章节的 character_intents 必须继承卷概览中该角色的整体意图方向，但做阶段性细化："
            "卷概览的角色意图是「本章想达成的目标」，子章节应将其拆解为「本节此刻想推动的具体一步」。"
            "禁止子章节的意图与卷概览方向矛盾或完全无关。"
        )
    else:
        char_intent_guidance = (
            "每个子章节的 character_intents 需标注：角色在本节的具体目标和最想要的信号/结果。"
            "不同子章节之间同一角色的意图应有递进关系（前一节的行动结果改变后一节的目标）。"
        )

    # 爽点派生指引
    if structure.get("shuang_design"):
        shuang_guidance = (
            "每个子章节的 shuang_design 从卷概览的爽点设计中派生："
            "卷概览给出了整卷的信息差和震惊层级，子章节需将大型爽点拆解为阶段性锚点。"
            "例如第1节预埋信息差（某角色知道而另一角色不知道），第2节推进（被蒙蔽者察觉异样），第3节引爆。"
        )
    else:
        shuang_guidance = (
            "每个子章节的 shuang_design 必须与子章节的具体情节绑定："
            "info_asymmetry 指明本节哪组角色之间存在信息差，"
            "spectator_layers 的围观者必须是本节实际出场或受本节事件影响的角色/组织。"
            "禁止使用「某路人」「围观群众」等抽象占位——必须用具体角色名或组织名。"
        )

    result = await engine.execute_skill(
        "outline_expand_single",
        ai_client,
        {
            "outline_order_index": str(outline.chapter_number),
            "outline_title": outline.title or "无标题",
            "outline_content": outline_content,
            "outline_summary": outline.summary or "",
            "target_chapter_count": str(target_chapter_count),
            "project_title": proj.title,
            "project_genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "characters_info": ctx["characters_info"],
            "world_info": ctx["world_info"],
            "organizations_info": ctx["organizations_info"],
            "context_info": context_info,
            "context_note": context_note,
            # 节奏变量（由 md 模板中的 <rhythm_rules> 使用）
            "focus_kps_text": focus_kps_text,
            "kp_allocation_rule": kp_allocation_rule,
            "no_focus_fallback": no_focus_fallback,
            "general_kps_rule": general_kps_rule,
            "weak_kps_rule": weak_kps_rule,
            "mode_extra": mode_extra,
            # 继承/派生指引（由 md 模板中的 <character_intent_rules> 和 <commercial_design_guide> 使用）
            "char_intent_guidance": char_intent_guidance,
            "shuang_guidance": shuang_guidance,
            "user_prompt": (
                f"请将第{outline.chapter_number}卷《{outline.title}》展开为{target_chapter_count}个子章节，返回JSON数组。{existing_context}"
            ),
        },
    )
    check_skill_error(result)
    expanded_data = result.get("json") or []
    if not isinstance(expanded_data, list):
        raise HTTPException(500, "AI 返回的展开格式不正确")

    # 计算起始章号
    if replace_existing and old_start_chapter is not None:
        # 覆盖模式：新章节从旧章节的起始号开始（保证章号连续，不留空洞）
        start_chapter = old_start_chapter
    else:
        # 新展开：取当前已存在的最大 chapter_number + 1，前置大纲未展开也不会冲突
        max_ch = await db.scalar(
            select(func.max(Chapter.chapter_number)).where(
                Chapter.project_id == project_id,
            )
        )
        start_chapter = (max_ch or 0) + 1

    # 创建 N 个 Chapter
    created = []
    for idx, plan in enumerate(expanded_data[:target_chapter_count]):
        if not isinstance(plan, dict):
            continue
        # 保留 AI 产出的全部字段（emotional_arc/hook/shuang_design/reader_hook/
        # rhythm_tag/scene_anchor/character_intents 等），不丢弃富信息
        plan_data = {**plan}
        # 标准字段兼容映射：emotional_arc → emotional_tone（供 chapter_context 读取）
        if plan.get("emotional_arc") and not plan.get("emotional_tone"):
            plan_data["emotional_tone"] = plan["emotional_arc"]
        # 剥离已单独存储的冗余字段，避免 expansion_plan JSON 和 Chapter 列重复
        for _strip_key in ("sub_index", "title", "estimated_words"):
            plan_data.pop(_strip_key, None)
        ch = Chapter(
            project_id=project_id,
            outline_id=outline_id,
            chapter_number=start_chapter + idx,
            sub_index=(append_base_sub_index + idx + 1) if append_existing else (idx + 1),
            title=plan.get("title", f"第{start_chapter + idx}章"),
            summary=(plan_data.get("plot_summary") or "")[:300],
            status="draft",
            generation_mode="one_to_many",
            expansion_plan=plan_data,
        )
        db.add(ch)
        created.append(
            {
                "chapter_number": start_chapter + idx,
                "sub_index": (append_base_sub_index + idx + 1) if append_existing else (idx + 1),
                "title": ch.title,
                "plot_summary": plan_data.get("plot_summary", ""),
                "key_events": plan_data.get("key_events", []),
            }
        )
    await db.commit()
    return {
        "expanded": created,
        "count": len(created),
        "start_chapter": start_chapter,
        "replaced": replaced_count,
        "appended": append_existing,
    }


@router.post("/{project_id}/outlines/{outline_id}/expand")
async def expand_outline(
    project_id: int,
    outline_id: int,
    req: OutlineExpandRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """大纲展开为多章（1对多模式核心，同步版）：AI 将一条大纲拆成 N 个章节计划，创建 N 个 Chapter。

    - 章号分配：取当前已存在最大 chapter_number + 1（避免前置未展开导致冲突）
    - 每个 Chapter 关联 outline_id，含 sub_index + expansion_plan
    """
    return await _expand_outline_core(db, project_id, outline_id, req.target_chapter_count, user.id)


@router.post("/{project_id}/outlines/{outline_id}/expand-async")
async def expand_outline_async(
    project_id: int,
    outline_id: int,
    req: OutlineExpandRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """大纲展开为多章（异步队列版）：立即返回 task_id，后台执行。

    三种模式（req.mode）：
    - new：首次展开，已展开则报错
    - replace：覆盖旧章节重新规划
    - append：在已有章节后追加（旧章节保留）

    完成后通过 WebSocket 推送，前端浮窗查看进度。task_type = outline_expand。
    """
    proj = await get_user_project(db, project_id, user)
    outline = (
        await db.execute(
            select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not outline:
        raise HTTPException(404, "大纲不存在")
    mode = (req.mode or "new").lower()
    if mode not in ("new", "replace", "append"):
        raise HTTPException(400, "mode 只能是 new / replace / append")
    # new 模式才校验「已展开」；replace/append 允许已存在章节
    if mode == "new":
        existing = (
            (
                await db.execute(
                    select(Chapter).where(
                        Chapter.outline_id == outline_id, Chapter.project_id == project_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if existing:
            raise HTTPException(400, f"此大纲已展开为 {len(existing)} 章，请先删除再重新展开")

    from app.services.async_ai_service import submit_async_task

    async def _run_expand(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        m = payload.get("mode", "new")
        tag = {"replace": "（覆盖旧章节）", "append": "（追加新章节）"}.get(m, "")
        await tracker.update(stage="preparing", message=f"准备展开大纲...{tag}")
        async with async_session() as task_db:
            await tracker.update(
                stage="generating", message=f"AI 正在展开为 {payload['target_chapter_count']} 章..."
            )
            res = await _expand_outline_core(
                task_db,
                payload["project_id"],
                payload["outline_id"],
                payload["target_chapter_count"],
                payload["user_id"],
                skip_existing_check=True,  # 提前校验过了
                replace_existing=(m == "replace"),
                append_existing=(m == "append"),
                strategy=payload.get("strategy", "balanced"),
            )
            await tracker.update(stage="saving", message="保存展开章节...")
        replaced = res.get("replaced", 0)
        appended = res.get("appended", False)
        if replaced:
            done_msg = f"已覆盖旧 {replaced} 章并重新展开为 {res['count']} 章（起始第{res['start_chapter']}章）"
        elif appended:
            done_msg = f"已追加 {res['count']} 章到第{res['start_chapter']}章"
        else:
            done_msg = f"已展开为 {res['count']} 章（起始第{res['start_chapter']}章）"
        await tracker.complete(message=done_msg, result=res)

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="outline_expand",
        title=f"展开第{outline.chapter_number}卷《{outline.title or ''}》",
        payload={
            "project_id": project_id,
            "outline_id": outline_id,
            "target_chapter_count": req.target_chapter_count,
            "user_id": user.id,
            "mode": mode,
            "strategy": req.strategy,
        },
        runner=_run_expand,
    )
    return {"task_id": task_id}


@router.post("/{project_id}/outlines/batch-expand-async")
async def batch_expand_outlines_async(
    project_id: int,
    req: BatchExpandRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量展开所有未展开的大纲（异步队列版）：一个后台任务内按序展开每卷。

    - 自动跳过已展开的大纲
    - 按大纲 order 逐卷展开（前置完成后再展开下一卷，保证章号连续）
    - progress_details 推送 {done, total, current_outline} 供前端显示进度
    - task_type = outline_expand（完成回调与单卷展开共用）

    请求体：
        target_chapter_count: int  每卷展开的章节数（默认 3）
    """
    proj = await get_user_project(db, project_id, user)
    if (proj.outline_mode or "one_to_one") != "one_to_many":
        raise HTTPException(400, "批量展开仅在「细化模式(1→N)」下可用")
    # 拉取所有大纲（按章号），确认有待展开项，避免建空任务
    outlines_all = (
        (
            await db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    # 查已展开的大纲ID集合（has_chapters 是 list_outlines 拼的虚拟字段，这里用 Chapter 表统计）
    expanded_ids: set = set()
    if outlines_all:
        rows = (
            await db.execute(
                select(Chapter.outline_id)
                .where(Chapter.project_id == project_id, Chapter.outline_id.isnot(None))
                .distinct()
            )
        ).all()
        expanded_ids = {r[0] for r in rows}
    pending = [o for o in outlines_all if o.id not in expanded_ids]
    if not pending:
        raise HTTPException(400, "没有可展开的大纲（所有大纲都已展开）")

    from app.services.async_ai_service import submit_async_task

    target_count = req.target_chapter_count
    pending_snapshot = [
        {"id": o.id, "chapter_number": o.chapter_number, "title": o.title or ""} for o in pending
    ]
    project_id_snap = project_id
    user_id_snap = user.id

    async def _run_batch_expand(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        items = payload["items"]
        total = len(items)
        await tracker.update(
            stage="preparing",
            message=f"准备批量展开 {total} 卷...",
            progress_details={"done": 0, "total": total},
        )
        done = 0
        failed = []
        total_chapters = 0
        for item in items:
            if await tracker.is_cancelled():
                await tracker.fail("用户已取消")
                return
            await tracker.update(
                stage="generating",
                message=f"正在展开第 {item['chapter_number']} 卷《{item['title']}》（{done + 1}/{total}）...",
                progress=int(20 + (done / total) * 65),
                progress_details={"done": done, "total": total, "current_outline": item},
            )
            try:
                async with async_session() as task_db:
                    res = await _expand_outline_core(
                        task_db,
                        payload["project_id"],
                        item["id"],
                        payload["target_chapter_count"],
                        payload["user_id"],
                        skip_existing_check=True,
                    )
                    total_chapters += res["count"]
            except HTTPException as e:
                # 单卷失败不阻断整体，记录后继续
                failed.append({"outline_id": item["id"], "title": item["title"], "error": e.detail})
                logger.warning(f"[batch-expand] 第{item['chapter_number']}卷展开失败: {e.detail}")
            except Exception as e:
                failed.append({"outline_id": item["id"], "title": item["title"], "error": str(e)})
                logger.warning(f"[batch-expand] 第{item['chapter_number']}卷展开异常: {e}")
            done += 1
            await tracker.update(
                stage="saving",
                message=f"已完成 {done}/{total} 卷",
                progress=int(20 + (done / total) * 72),
                progress_details={"done": done, "total": total, "current_outline": item},
            )

        summary = f"批量展开完成：{total} 卷 → {total_chapters} 章" + (
            f"，{len(failed)} 卷失败" if failed else ""
        )
        await tracker.complete(
            message=summary,
            result={"total_outlines": total, "total_chapters": total_chapters, "failed": failed},
        )

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id_snap,
        task_type="outline_expand",
        title=f"批量展开 {len(pending)} 卷大纲",
        payload={
            "project_id": project_id_snap,
            "user_id": user_id_snap,
            "items": pending_snapshot,
            "target_chapter_count": target_count,
        },
        runner=_run_batch_expand,
    )
    return {"task_id": task_id, "pending_count": len(pending)}


@router.get("/{project_id}/outlines/{outline_id}/chapters")
async def get_outline_chapters(
    project_id: int,
    outline_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """查询某大纲展开的所有章节（1对多用）。"""
    await get_user_project(db, project_id, user)
    chapters = (
        (
            await db.execute(
                select(Chapter)
                .where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
                .order_by(Chapter.sub_index)
            )
        )
        .scalars()
        .all()
    )
    return {
        "has_chapters": len(chapters) > 0,
        "chapter_count": len(chapters),
        "chapters": [
            {
                "id": c.id,
                "chapter_number": c.chapter_number,
                "sub_index": c.sub_index,
                "title": c.title,
                "summary": c.summary,
                "status": c.status,
                "expansion_plan": c.expansion_plan,
            }
            for c in chapters
        ],
    }


@router.delete("/{project_id}/outlines/{outline_id}/chapters")
async def delete_outline_chapters(
    project_id: int,
    outline_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除某大纲展开的所有章节（1对多模式下重新展开用）。"""
    await get_user_project(db, project_id, user)
    chapters = (
        (
            await db.execute(
                select(Chapter).where(
                    Chapter.outline_id == outline_id, Chapter.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    count = len(chapters)
    if chapters:
        # 先清理关联的 PlotAnalysis / StoryMemory / 向量 / 分析伏笔 / GenerationHistory
        chapter_service = ChapterService(db, project_id, user_id=user.id)
        await chapter_service.cleanup_chapters_data([c.id for c in chapters])
        # 再删除章节本身
        for c in chapters:
            await db.delete(c)
    await db.commit()
    return {"ok": True, "deleted": count}
