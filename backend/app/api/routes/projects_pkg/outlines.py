"""大纲：生成 / CRUD / 续写 / 展开"""
import asyncio
import json
import logging
from app.api.routes.projects_pkg.base import *
from app.core.database import async_session
from app.services.outline_validation_service import validate_outline_entities, build_world_context
from app.services.chapter_tools import get_chapter_tools, make_tool_executor

logger = logging.getLogger(__name__)


router = make_router()

# 组织名关键词：用于兜底判断 characters 中的名称是否实为组织
_ORG_KEYWORDS = ("议会", "帮", "派", "门", "宗", "盟", "阁", "会", "部", "团", "社", "局", "庭", "族", "学院", "教会", "帝国", "王国", "殿", "堂", "塔")


def _extract_names(lst: list) -> list:
    """从列表中提取 (名称, 类型) 对，兼容字符串和 {name:...} 两种格式。"""
    result = []
    for ch in (lst or []):
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


def _build_outline(project_id: int, item: dict, offset: int = 0, index: int = 0,
                  char_names: set = None, org_names: set = None) -> Outline:
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
    final_chars, final_orgs = _separate_chars_orgs(raw_chars, raw_orgs, char_names or set(), org_names or set())

    # 安全网：如果 AI 明确返回了角色但被过滤光了，保留 AI 原始值
    if not final_chars and raw_chars:
        raw_names = [c if isinstance(c, str) else c.get("name", "") for c in raw_chars if isinstance(c, (str, dict))]
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

    must = []       # 本次必须回收
    overdue = []    # 超期
    upcoming = []   # 下一批
    future = []     # 远期
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
            lines.append(f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章，优先:{f.priority or 5}）")
        parts.append("\n".join(lines))

    if overdue:
        lines = ["⚠️ 【已超期未回收（请尽快安排）】"]
        for f in overdue:
            lines.append(f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章，已超期）")
        parts.append("\n".join(lines))

    if upcoming:
        lines = ["⏰ 【下一批即将到期（第{}章前）】".format(end_chapter + 10)]
        for f in upcoming:
            lines.append(f"  - {f.title}：{f.content or ''}（目标第{f.target_resolve_chapter_number}章）")
        parts.append("\n".join(lines))

    if plant_now:
        lines = ["🌱 【本次应埋入的伏笔】"]
        for f in plant_now:
            lines.append(f"  - {f.title}：{f.content or ''}（计划在第{f.plant_chapter_number}章埋入，第{f.target_resolve_chapter_number or '?'}章回收）")
        parts.append("\n".join(lines))

    if future:
        lines = ["📋 【远期伏笔（可铺垫，不必立即回收）】"]
        for f in future:
            target_str = f"目标第{f.target_resolve_chapter_number}章" if f.target_resolve_chapter_number else "未指定回收章节"
            lines.append(f"  - {f.title}：{f.content or ''}（{target_str}）")
        parts.append("\n".join(lines))

    return "\n\n".join(parts) if parts else "暂无伏笔"


async def _project_context(db: AsyncSession, project_id: int, project: Project, use_tools: bool = False) -> dict:
    """收集项目的世界观/角色/组织上下文信息（生成大纲时复用）。

    分层策略：近的全量、远的精简。
    - 主角/反派 → 完整信息
    - 最近章节涉及的配角 → 中等信息
    - 其他角色 → 仅名字+定位

    如果 use_tools=True（AI 有工具调用能力），则精简上下文：
    只发核心世界观 + 角色名单，不传详细设定。AI 首次调用时通过
    list_available_entities + query_* 工具按需获取信息，大幅节省首轮 token。
    """
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    orgs = (await db.execute(select(Organization).where(Organization.project_id == project_id))).scalars().all()

    # 世界设定：核心四维度始终发送；详细设定仅非工具模式发送
    core_parts = []
    if project.world_time_period: core_parts.append(f"时间背景：{project.world_time_period}")
    if project.world_location: core_parts.append(f"地理位置：{project.world_location}")
    if project.world_atmosphere: core_parts.append(f"氛围基调：{project.world_atmosphere}")
    if project.world_rules: core_parts.append(f"世界规则：{project.world_rules}")
    core = "\n".join(core_parts)

    if use_tools:
        # 工具模式：角色信息照样发（系统直接提供），世界设定条目不传，引导 AI 用工具查
        detail_items = ""  # 不传详细设定，AI 通过工具按需查询
        tool_hint = (
            "\n\n💡 世界设定条目（地理/历史/文化等）、组织详情、地点信息等辅助资料可通过工具查询。"
            "角色信息已提供，无需查询。建议先调用 list_available_entities 了解可查内容。"
        )
        world_info = ("【核心世界观】\n" + (core or "暂无") + tool_hint)
    else:
        detail_items = "\n".join([f"- {w.name}({w.category or ''})：{w.content[:150]}" for w in worlds[:10]])
        world_info = ("【核心世界观】\n" + core + "\n【详细设定】\n" + detail_items) if detail_items else (core or "暂无")

    # 角色：分层注入（无论工具模式都发，角色信息由系统直接提供，不走工具查询）
    char_parts = []
    # 查最近大纲中涉及的角色名（用于判断"最近活跃"）
    recent_char_names = set()
    try:
        recent_outlines = (await db.execute(
            select(Outline).where(Outline.project_id == project_id)
            .order_by(Outline.chapter_number.desc()).limit(5)
        )).scalars().all()
        for o in recent_outlines:
            if o.characters and isinstance(o.characters, list):
                for c in o.characters:
                    recent_char_names.add(str(c).strip() if isinstance(c, str) else c.get("name", ""))
    except Exception:
        pass

    for c in chars:
        is_core = c.role in ("主角", "反派")
        is_recent = c.name in recent_char_names or not recent_char_names

        if is_core:
            lines = [f"- {c.name}（{c.role}，{c.gender or ''}，{c.age or '?'}岁）"]
            if c.identity: lines.append(f"  身份：{c.identity}")
            if c.personality: lines.append(f"  性格：{c.personality}")
            if c.background: lines.append(f"  背景：{c.background}")
            if c.story_goal: lines.append(f"  目标：{c.story_goal}")
            if c.motivation: lines.append(f"  动机：{c.motivation}")
            if c.weakness: lines.append(f"  弱点：{c.weakness}")
            if c.occupation: lines.append(f"  职业：{c.occupation}")
            if c.ability: lines.append(f"  能力：{c.ability}")
            char_parts.append("\n".join(lines))
        elif is_recent:
            lines = [f"- {c.name}（{c.role}，{c.gender or ''}）"]
            if c.personality: lines.append(f"  性格：{c.personality[:120]}")
            if c.occupation: lines.append(f"  职业：{c.occupation}")
            if c.story_goal: lines.append(f"  目标：{c.story_goal[:80]}")
            char_parts.append("\n".join(lines))
        else:
            char_parts.append(f"- {c.name}（{c.role}）")

    chars_info = "\n\n".join(char_parts) if char_parts else "暂无"

    # 组织：全部显示但限制长度（工具模式跳过）
    orgs_info = ""
    if not use_tools:
        orgs_info = "\n".join(
            [f"- {o.name}（{o.org_type or '组织'}，势力值{o.power_value or 50}）：{o.description or ''}" for o in orgs]
        ) or "暂无"

    char_names = {c.name for c in chars}
    org_names = {o.name for o in orgs}
    return {
        "world_info": world_info,
        "characters_info": chars_info,
        "organizations_info": orgs_info,
        "char_names": char_names,
        "org_names": org_names,
        "time_period": project.world_time_period or "",
        "location": project.world_location or "",
        "atmosphere": project.world_atmosphere or "",
        "rules": project.world_rules or "",
    }


@router.post("/{project_id}/outlines/generate")
async def generate_outlines(project_id: int, req: OutlineGenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    project = await get_user_project(db, project_id, user)
    ctx = await _project_context(db, project_id, project, use_tools=True)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("outline_create", ai_client, {
        **ctx,
        "title": project.title,
        "genre": project.genre or "网文",
        "theme": project.genre or "网文",
        "synopsis": project.synopsis or "暂无简介",
        "chapter_count": str(req.chapter_count),
        "narrative_perspective": project.narrative_pov or "第三人称",
        "narrative_pov": project.narrative_pov or "第三人称",
        "mcp_references": "",
        "requirements": "",
        "user_prompt": f"请为《{project.title}》生成{req.chapter_count}章大纲。如需确认角色、组织、伏笔等，可使用工具查询。",
    }, tools=get_chapter_tools(), tool_executor=make_tool_executor(db, project_id, req.chapter_count + 1))
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    created_outline_objs = []
    for idx, item in enumerate(outlines_data):
        o = _build_outline(project_id, item, index=idx, char_names=ctx["char_names"], org_names=ctx["org_names"])
        db.add(o)
        created_outline_objs.append(o)
        created.append(item)
    await db.flush()  # 拿到 outline.id

    # 1对1模式：自动为每条大纲创建对应章节（章号=chapter_number，outline_id=NULL）
    # 1对多模式：只存大纲，不创建章节（用户后续手动"展开为多章"）
    if (project.outline_mode or "one_to_one") == "one_to_one":
        for o in created_outline_objs:
            # 检查是否已存在同章号的章节
            existing = (await db.execute(
                select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == o.chapter_number)
            )).scalars().first()
            if existing:
                continue
            ch = Chapter(
                project_id=project_id,
                chapter_number=o.chapter_number,
                title=o.title,
                summary=o.summary[:200] if o.summary else "",
                status="draft",
                outline_id=None,  # 1对1不关联
                sub_index=1,
                generation_mode="one_to_one",
            )
            db.add(ch)
        await db.commit()
    await db.commit()

    # 验证大纲中涉及的角色/组织是否都已创建
    world_ctx = build_world_context(project)
    asyncio.create_task(validate_outline_entities(db, project_id, project.title, project.genre or "网文", world_ctx, engine, ai_client))

    return {"outlines": created, "count": len(created)}

@router.post("/{project_id}/outlines/generate-async")
async def generate_outlines_async(project_id: int, req: OutlineGenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
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
            proj = await get_user_project(task_db, payload["project_id"], type("U", (), {"id": payload["user_id"]})())
            logger.info(f"[outline:{task_id}] project ok, building context...")
            ctx = await _project_context(task_db, payload["project_id"], proj)
            logger.info(f"[outline:{task_id}] context ok ({len(str(ctx))} chars), creating engine...")
            engine, ai_client = await make_engine_and_client(task_db, payload["user_id"])
            logger.info(f"[outline:{task_id}] engine ok, calling AI...")
            await tracker.update(stage="generating", message=f"AI 正在生成{payload['chapter_count']}章大纲...")
            result = await engine.execute_skill("outline_create", ai_client, {
                **ctx,
                "title": proj.title,
                "genre": proj.genre or "网文",
                "theme": proj.genre or "网文",
                "synopsis": proj.synopsis or "暂无简介",
                "chapter_count": str(payload["chapter_count"]),
                "narrative_perspective": proj.narrative_pov or "第三人称",
                "narrative_pov": proj.narrative_pov or "第三人称",
                "mcp_references": "",
                "requirements": "",
                "user_prompt": f"请为《{proj.title}》生成{payload['chapter_count']}章大纲。如需查询角色、组织、伏笔等，可使用工具。",
            }, tools=get_chapter_tools(), tool_executor=make_tool_executor(task_db, payload["project_id"], payload["chapter_count"] + 1))
            if result.get("error"):
                await tracker.fail(result["error"])
                return
            await tracker.update(stage="saving", message="保存大纲...")
            outlines_data = result.get("json") or []
            if isinstance(outlines_data, list):
                created_objs = []
                for idx, item in enumerate(outlines_data):
                    o = _build_outline(payload["project_id"], item, index=idx, char_names=ctx["char_names"], org_names=ctx["org_names"])
                    task_db.add(o)
                    created_objs.append(o)
                await task_db.flush()
                if (proj.outline_mode or "one_to_one") == "one_to_one":
                    for o in created_objs:
                        existing = (await task_db.execute(
                            select(Chapter).where(Chapter.project_id == payload["project_id"], Chapter.chapter_number == o.chapter_number)
                        )).scalars().first()
                        if existing:
                            continue
                        ch = Chapter(
                            project_id=payload["project_id"], chapter_number=o.chapter_number,
                            title=o.title, summary=o.summary[:200] if o.summary else "",
                            status="draft", outline_id=None, sub_index=1, generation_mode="one_to_one",
                        )
                        task_db.add(ch)
                await task_db.commit()
            await tracker.complete(message=f"大纲生成完成（{len(outlines_data)}章）")

    task_id = await submit_async_task(
        user_id=user.id, project_id=project_id,
        task_type="outline_new",
        title="生成大纲",
        payload={"chapter_count": req.chapter_count, "project_id": project_id, "user_id": user.id},
        runner=_run_outline,
    )
    return {"task_id": task_id}


@router.get("/{project_id}/outlines")
async def list_outlines(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    # 预查每个大纲关联的章节数（1对多用）
    from sqlalchemy import func
    chapter_counts = {}
    if outlines:
        rows = (await db.execute(
            select(Chapter.outline_id, func.count(Chapter.id))
            .where(Chapter.project_id == project_id, Chapter.outline_id.isnot(None))
            .group_by(Chapter.outline_id)
        )).all()
        chapter_counts = {r[0]: r[1] for r in rows}
    return [{
        "id": o.id, "chapter_number": o.chapter_number, "title": o.title,
        "summary": o.summary, "scenes": o.scenes, "characters": o.characters,
        "key_points": o.key_points, "emotion": o.emotion, "goal": o.goal,
        "structure": o.structure or {},  # 含 AI 生成的全部额外字段（爽点/钩子/伏笔/组织等）
        "has_chapters": chapter_counts.get(o.id, 0) > 0,
        "chapter_count": chapter_counts.get(o.id, 0),
    } for o in outlines]


@router.post("/{project_id}/outlines")
async def create_outline(project_id: int, req: OutlineCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    o = Outline(project_id=project_id, **req.model_dump())
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return {"id": o.id}


@router.put("/{project_id}/outlines/{outline_id}")
async def update_outline(project_id: int, outline_id: int, req: OutlineCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    o = (await db.execute(select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "大纲不存在")
    for key, value in req.model_dump().items():
        setattr(o, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/outlines/{outline_id}")
async def delete_outline(project_id: int, outline_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    o = (await db.execute(select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id))).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "大纲不存在")
    await db.delete(o)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/outlines/continue")
async def continue_outlines(project_id: int, req: OutlineContinueRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """大纲续写：在现有大纲基础上继续生成。

    上下文优化：
    - 最近 N 章大纲传完整版（title + summary + key_points）
    - 更早的大纲传精简版（chapter_number + title + summary）
    - 超过 30 条时进一步压缩为每 5 章一条摘要
    """
    from app.core.config import settings

    proj = await get_user_project(db, project_id, user)
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    chapters = (await db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number))).scalars().all()
    foreshadows_list = (await db.execute(select(Foreshadow).where(Foreshadow.project_id == project_id, Foreshadow.status.in_(["pending", "planted"])))).scalars().all()
    ctx = await _project_context(db, project_id, proj, use_tools=True)

    # ===== 大纲上下文截断优化 =====
    full_limit = settings.OUTLINE_CONTEXT_CHAPTERS  # 默认 20
    if len(outlines) <= full_limit:
        # 章节数不多，全部传完整版
        recent_outlines_json = json.dumps([
            {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary, "key_points": o.key_points}
            for o in outlines
        ], ensure_ascii=False)
    else:
        # 最近 N 章：完整版
        recent = outlines[-full_limit:]
        older = outlines[:-full_limit]
        # 更早的章节：精简版（去掉 key_points/scenes）
        older_brief = [
            {"chapter_number": o.chapter_number, "title": o.title, "summary": (o.summary or "")[:200]}
            for o in older
        ]
        # 如果精简后仍然超过 30 条，进一步压缩为每 5 章一条
        if len(older_brief) > 30:
            compressed = []
            for i in range(0, len(older_brief), 5):
                chunk = older_brief[i:i+5]
                first, last = chunk[0], chunk[-1]
                summaries = "；".join(c["summary"][:30] for c in chunk if c["summary"])
                compressed.append({
                    "chapter_number": f"{first['chapter_number']}-{last['chapter_number']}",
                    "title": f"第{first['chapter_number']}-{last['chapter_number']}章概要",
                    "summary": summaries[:200],
                })
            older_brief = compressed
        # 合并：精简版 + 完整版
        recent_outlines_json = json.dumps(older_brief + [
            {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary, "key_points": o.key_points}
            for o in recent
        ], ensure_ascii=False)

    existing_chapters = json.dumps([{"chapter_number": c.chapter_number, "title": c.title, "summary": c.summary or ""} for c in chapters], ensure_ascii=False) if chapters else "暂无"

    current_count = max((o.chapter_number for o in outlines), default=0)
    start_chapter, end_chapter = current_count + 1, current_count + req.chapter_count

    foreshadow_context = _format_foreshadows_for_outline(foreshadows_list, start_chapter, end_chapter)

    # 叙事视角：前端留空 = 按小说设定（取项目默认）
    effective_pov = req.narrative_pov or proj.narrative_pov or "第三人称"

    engine, ai_client = await make_engine_and_client(db, user.id, model_override=(req.ai_model or None))
    # 拼装用户额外要求（故事方向/情节阶段/其他要求）
    extra_req_parts = []
    if req.story_direction:
        extra_req_parts.append(f"故事发展方向：{req.story_direction}")
    if req.plot_stage:
        extra_req_parts.append(f"当前情节阶段：{req.plot_stage}")
    if req.other_requirements:
        extra_req_parts.append(f"其他要求：{req.other_requirements}")
    extra_req_text = ("\n".join(extra_req_parts) + "\n") if extra_req_parts else ""

    result = await engine.execute_skill("outline_continue", ai_client, {
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
    }, tools=get_chapter_tools(), tool_executor=make_tool_executor(db, project_id, start_chapter))
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    created_objs = []
    for item in outlines_data:
        o = _build_outline(project_id, item, char_names=ctx["char_names"], org_names=ctx["org_names"])
        db.add(o)
        created_objs.append(o)
        created.append(item)
    await db.flush()

    # 1对1模式：自动为续写的大纲创建对应章节
    if (proj.outline_mode or "one_to_one") == "one_to_one":
        for o in created_objs:
            existing = (await db.execute(
                select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == o.chapter_number)
            )).scalars().first()
            if existing:
                continue
            ch = Chapter(
                project_id=project_id, chapter_number=o.chapter_number,
                title=o.title, summary=o.summary[:200] if o.summary else "",
                status="draft", outline_id=None, sub_index=1, generation_mode="one_to_one",
            )
            db.add(ch)
    await db.commit()

    # ===== 新角色检测 =====
    # 从新生成的大纲中提取角色名，与已有角色对比，找出未注册的角色
    existing_chars = {c.name for c in (await db.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()}
    existing_org_names = {o.name for o in (await db.execute(
        select(Organization).where(Organization.project_id == project_id)
    )).scalars().all()}
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
    asyncio.create_task(validate_outline_entities(db, project_id, proj.title, proj.genre or "网文", world_ctx, ai_client))

    return response


@router.post("/{project_id}/outlines/continue-async")
async def continue_outlines_async(project_id: int, req: OutlineContinueRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
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
            proj = await get_user_project(task_db, payload["project_id"], type("U", (), {"id": payload["user_id"]})())
            outlines = (await task_db.execute(select(Outline).where(Outline.project_id == payload["project_id"]).order_by(Outline.chapter_number))).scalars().all()
            current_count = max((o.chapter_number for o in outlines), default=0)
            await tracker.update(stage="generating", message=f"AI 续写第{current_count+1}到{current_count+payload['chapter_count']}章...")
            # 调用同步版本的核心逻辑
            from app.api.routes.projects_pkg.outlines import continue_outlines as _co
            # 直接调用路由函数太复杂，这里内联核心逻辑
            ctx = await _project_context(task_db, payload["project_id"], proj)
            from app.core.config import settings
            full_limit = settings.OUTLINE_CONTEXT_CHAPTERS
            if len(outlines) <= full_limit:
                recent_outlines_json = json.dumps([
                    {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary, "key_points": o.key_points}
                    for o in outlines
                ], ensure_ascii=False)
            else:
                recent = outlines[-full_limit:]
                older = outlines[:-full_limit]
                older_brief = [
                    {"chapter_number": o.chapter_number, "title": o.title, "summary": (o.summary or "")[:200]}
                    for o in older
                ]
                if len(older_brief) > 30:
                    compressed = []
                    for i in range(0, len(older_brief), 5):
                        chunk = older_brief[i:i+5]
                        first, last = chunk[0], chunk[-1]
                        summaries = "；".join(c["summary"][:30] for c in chunk if c["summary"])
                        compressed.append({
                            "chapter_number": f"{first['chapter_number']}-{last['chapter_number']}",
                            "title": f"第{first['chapter_number']}-{last['chapter_number']}章概要",
                            "summary": summaries[:200],
                        })
                    older_brief = compressed
                recent_outlines_json = json.dumps(older_brief + [
                    {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary, "key_points": o.key_points}
                    for o in recent
                ], ensure_ascii=False)
            chapters = (await task_db.execute(select(Chapter).where(Chapter.project_id == payload["project_id"]).order_by(Chapter.chapter_number))).scalars().all()
            existing_chapters = json.dumps([{"chapter_number": c.chapter_number, "title": c.title, "summary": c.summary or ""} for c in chapters], ensure_ascii=False) if chapters else "暂无"
            foreshadows_list = (await task_db.execute(select(Foreshadow).where(Foreshadow.project_id == payload["project_id"], Foreshadow.status.in_(["pending", "planted"])))).scalars().all()
            start_chapter, end_chapter = current_count + 1, current_count + payload["chapter_count"]
            foreshadow_context = _format_foreshadows_for_outline(foreshadows_list, start_chapter, end_chapter)
            # 叙事视角：前端留空 = 按小说设定
            effective_pov = payload.get("narrative_pov") or proj.narrative_pov or "第三人称"
            engine, ai_client = await make_engine_and_client(task_db, payload["user_id"], model_override=(payload.get("ai_model") or None))
            # 拼装用户额外要求
            extra_req_parts = []
            if payload.get("story_direction"):
                extra_req_parts.append(f"故事发展方向：{payload['story_direction']}")
            if payload.get("plot_stage"):
                extra_req_parts.append(f"当前情节阶段：{payload['plot_stage']}")
            if payload.get("other_requirements"):
                extra_req_parts.append(f"其他要求：{payload['other_requirements']}")
            extra_req_text = ("\n".join(extra_req_parts) + "\n") if extra_req_parts else ""
            result = await engine.execute_skill("outline_continue", ai_client, {
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
            }, tools=get_chapter_tools(), tool_executor=make_tool_executor(task_db, payload["project_id"], start_chapter))
            if result.get("error"):
                await tracker.fail(result["error"])
                return
            await tracker.update(stage="saving", message="保存大纲...")
            outlines_data = result.get("json") or []
            if isinstance(outlines_data, list):
                created_objs = []
                for item in outlines_data:
                    o = _build_outline(payload["project_id"], item, char_names=ctx["char_names"], org_names=ctx["org_names"])
                    task_db.add(o)
                    created_objs.append(o)
                await task_db.flush()
                # 1对1模式：自动为续写的大纲创建对应章节
                if (proj.outline_mode or "one_to_one") == "one_to_one":
                    for o in created_objs:
                        existing = (await task_db.execute(
                            select(Chapter).where(Chapter.project_id == payload["project_id"], Chapter.chapter_number == o.chapter_number)
                        )).scalars().first()
                        if existing:
                            continue
                        ch = Chapter(
                            project_id=payload["project_id"], chapter_number=o.chapter_number,
                            title=o.title, summary=o.summary[:200] if o.summary else "",
                            status="draft", outline_id=None, sub_index=1, generation_mode="one_to_one",
                        )
                        task_db.add(ch)
                await task_db.commit()
            await tracker.complete(message=f"续写完成（{len(outlines_data)}章）")

    task_id = await submit_async_task(
        user_id=user.id, project_id=project_id,
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


@router.post("/{project_id}/outlines/{outline_id}/expand")
async def expand_outline(project_id: int, outline_id: int, req: OutlineExpandRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """大纲展开为多章（1对多模式核心）：AI 将一条大纲拆成 N 个章节计划，创建 N 个 Chapter。

    - 章号分配：当前大纲起始章号 = 前置所有大纲（chapter_number 更小）已展开的章节数总和 + 1
    - 每个 Chapter 关联 outline_id，含 sub_index + expansion_plan
    """
    proj = await get_user_project(db, project_id, user)
    outline = (await db.execute(select(Outline).where(Outline.id == outline_id, Outline.project_id == project_id))).scalar_one_or_none()
    if not outline:
        raise HTTPException(404, "大纲不存在")
    # 若已展开则不允许重复
    existing_chapters = (await db.execute(
        select(Chapter).where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
    )).scalars().all()
    if existing_chapters:
        raise HTTPException(400, f"此大纲已展开为 {len(existing_chapters)} 章，请先删除再重新展开")

    ctx = await _project_context(db, project_id, proj, use_tools=True)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("outline_expand_single", ai_client, {
        "outline_order_index": str(outline.chapter_number), "outline_title": outline.title or "无标题",
        "outline_summary": outline.summary or "", "target_chapter_count": str(req.target_chapter_count),
        "project_title": proj.title, "project_genre": proj.genre or "网文", "synopsis": proj.synopsis or "暂无简介",
        "characters_info": ctx["characters_info"], "world_info": ctx["world_info"],
        "organizations_info": ctx["organizations_info"],
        "user_prompt": f"请将第{outline.chapter_number}卷大纲「{outline.title}」展开为{req.target_chapter_count}个子章节。每个子章节需含：sub_index(序号)、title(标题)、plot_summary(200-300字剧情摘要)、key_events(关键事件列表)、character_focus(聚焦角色)、emotional_tone(情感基调)、narrative_goal(叙事目标)、conflict_type(冲突类型)。返回JSON数组。",
    })
    check_skill_error(result)
    expanded_data = result.get("json") or []
    if not isinstance(expanded_data, list):
        raise HTTPException(500, "AI 返回的展开格式不正确")

    # 计算起始章号
    # 策略：取当前已存在的最大 chapter_number + 1（而非累加前置大纲章节数）
    # 这样即使前置大纲未展开，章号也不会冲突
    max_ch = await db.scalar(select(func.max(Chapter.chapter_number)).where(
        Chapter.project_id == project_id,
    ))
    start_chapter = (max_ch or 0) + 1

    # 创建 N 个 Chapter
    created = []
    for idx, plan in enumerate(expanded_data[:req.target_chapter_count]):
        if not isinstance(plan, dict):
            continue
        plan_data = {
            "plot_summary": plan.get("plot_summary", plan.get("summary", "")),
            "key_events": plan.get("key_events", []),
            "character_focus": plan.get("character_focus", []),
            "emotional_tone": plan.get("emotional_tone", ""),
            "narrative_goal": plan.get("narrative_goal", ""),
            "conflict_type": plan.get("conflict_type", ""),
            "estimated_words": plan.get("estimated_words", 3000),
            "scenes": plan.get("scenes", []),
        }
        ch = Chapter(
            project_id=project_id,
            outline_id=outline_id,
            chapter_number=start_chapter + idx,
            sub_index=idx + 1,
            title=plan.get("title", f"第{start_chapter + idx}章"),
            summary=plan_data["plot_summary"][:300] if plan_data["plot_summary"] else "",
            status="draft",
            generation_mode="one_to_many",
            expansion_plan=plan_data,
        )
        db.add(ch)
        created.append({
            "chapter_number": start_chapter + idx,
            "sub_index": idx + 1,
            "title": ch.title,
            "plot_summary": plan_data["plot_summary"],
            "key_events": plan_data["key_events"],
        })
    await db.commit()
    return {"expanded": created, "count": len(created), "start_chapter": start_chapter}


@router.get("/{project_id}/outlines/{outline_id}/chapters")
async def get_outline_chapters(project_id: int, outline_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """查询某大纲展开的所有章节（1对多用）。"""
    await get_user_project(db, project_id, user)
    chapters = (await db.execute(
        select(Chapter).where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
        .order_by(Chapter.sub_index)
    )).scalars().all()
    return {
        "has_chapters": len(chapters) > 0,
        "chapter_count": len(chapters),
        "chapters": [{
            "id": c.id, "chapter_number": c.chapter_number, "sub_index": c.sub_index,
            "title": c.title, "summary": c.summary, "status": c.status,
            "expansion_plan": c.expansion_plan,
        } for c in chapters],
    }


@router.delete("/{project_id}/outlines/{outline_id}/chapters")
async def delete_outline_chapters(project_id: int, outline_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除某大纲展开的所有章节（1对多模式下重新展开用）。"""
    await get_user_project(db, project_id, user)
    chapters = (await db.execute(
        select(Chapter).where(Chapter.outline_id == outline_id, Chapter.project_id == project_id)
    )).scalars().all()
    count = len(chapters)
    for c in chapters:
        await db.delete(c)
    await db.commit()
    return {"ok": True, "deleted": count}