"""大纲：生成 / CRUD / 续写 / 展开"""
import json
import logging
from app.api.routes.projects_pkg.base import *

logger = logging.getLogger(__name__)


router = make_router()


def _build_outline(project_id: int, item: dict, offset: int = 0, index: int = 0) -> Outline:
    """从 AI 返回的 item 构造 Outline 对象（复用）。

    index 用于 AI 没返回 chapter_number 时自动编号（1-based）。
    """
    ch_num = item.get("chapter_number")
    if not isinstance(ch_num, int) or ch_num < 1:
        ch_num = index + 1  # AI 没返回或非法时，用序号
    return Outline(
        project_id=project_id,
        chapter_number=ch_num + offset,
        title=str(item.get("title", f"第{ch_num}章"))[:200],
        summary=str(item.get("summary", ""))[:2000],
        scenes=item.get("scenes", []) if isinstance(item.get("scenes"), list) else [],
        characters=item.get("characters", []) if isinstance(item.get("characters"), list) else [],
        key_points=item.get("key_points", []) if isinstance(item.get("key_points"), list) else [],
        emotion=str(item.get("emotion", ""))[:100],
        goal=str(item.get("goal", ""))[:200],
        structure=item,
    )


async def _project_context(db: AsyncSession, project_id: int, project: Project) -> dict:
    """收集项目的世界观/角色上下文信息（生成大纲时复用）。

    世界信息包含核心世界观（时间/地点/氛围/规则）+ 详细设定条目。
    """
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    detail = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds])
    # 核心世界观（存于 Project 字段）
    core_parts = []
    if project.world_time_period: core_parts.append(f"时间背景：{project.world_time_period}")
    if project.world_location: core_parts.append(f"地理位置：{project.world_location}")
    if project.world_atmosphere: core_parts.append(f"氛围基调：{project.world_atmosphere}")
    if project.world_rules: core_parts.append(f"世界规则：{project.world_rules}")
    core = "\n".join(core_parts)
    world_info = ("【核心世界观】\n" + core + "\n【详细设定】\n" + detail) if core else (detail or "暂无")
    chars_info = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    return {"world_info": world_info, "characters_info": chars_info}


@router.post("/{project_id}/outlines/generate")
async def generate_outlines(project_id: int, req: OutlineGenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    project = await get_user_project(db, project_id, user)
    ctx = await _project_context(db, project_id, project)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("outline_create", ai_client, {
        **ctx,
        "synopsis": project.synopsis or "暂无简介",
        "chapter_count": str(req.chapter_count),
        "user_prompt": f"请为这部{project.genre or '网文'}生成{req.chapter_count}章大纲。题材：{project.genre}，简介：{project.synopsis}",
    })
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    created_outline_objs = []
    for idx, item in enumerate(outlines_data):
        o = _build_outline(project_id, item, index=idx)
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
    return {"outlines": created, "count": len(created)}


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
    ctx = await _project_context(db, project_id, proj)

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
    foreshadow_context = "\n".join([f"- {f.title}({f.status}): {f.content[:100]}" for f in foreshadows_list]) or "暂无"

    current_count = max((o.chapter_number for o in outlines), default=0)
    start_chapter, end_chapter = current_count + 1, current_count + req.chapter_count

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("outline_continue", ai_client, {
        "genre": proj.genre or "网文", "title": proj.title, "synopsis": proj.synopsis or "暂无简介",
        "chapter_count": str(req.chapter_count), "current_chapter_count": str(current_count),
        "start_chapter": str(start_chapter), "end_chapter": str(end_chapter),
        "total_planned_chapters": str(current_count + req.chapter_count),
        "recent_outlines": recent_outlines_json, "existing_chapters": existing_chapters,
        "characters_info": ctx["characters_info"], "world_info": ctx["world_info"],
        "foreshadow_context": foreshadow_context,
        "foreshadow_reminders": foreshadow_context,  # 兼容模板中的变量名
        "narrative_pov": proj.narrative_pov or "第三人称", "narrative_perspective": proj.narrative_pov or "第三人称",
        "user_prompt": f"请在已有大纲（共{current_count}章）基础上，续写第{start_chapter}到{end_chapter}章的大纲。",
    })
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    for item in outlines_data:
        db.add(_build_outline(project_id, item))
        created.append(item)
    await db.commit()

    # ===== 新角色检测 =====
    # 从新生成的大纲中提取角色名，与已有角色对比，找出未注册的角色
    existing_chars = {c.name for c in (await db.execute(
        select(Character).where(Character.project_id == project_id)
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
            if name and name not in existing_chars:
                new_characters.add(name)

    response = {"outlines": created, "count": len(created)}
    if new_characters:
        response["new_characters"] = list(new_characters)
    return response


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

    ctx = await _project_context(db, project_id, proj)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("outline_expand_single", ai_client, {
        "outline_order_index": str(outline.chapter_number), "outline_title": outline.title or "无标题",
        "outline_summary": outline.summary or "", "target_chapter_count": str(req.target_chapter_count),
        "project_title": proj.title, "project_genre": proj.genre or "网文", "synopsis": proj.synopsis or "暂无简介",
        "characters_info": ctx["characters_info"], "world_info": ctx["world_info"],
        "user_prompt": f"请将第{outline.chapter_number}卷大纲「{outline.title}」展开为{req.target_chapter_count}个子章节。每个子章节需含：sub_index(序号)、title(标题)、plot_summary(200-300字剧情摘要)、key_events(关键事件列表)、character_focus(聚焦角色)、emotional_tone(情感基调)、narrative_goal(叙事目标)、conflict_type(冲突类型)。返回JSON数组。",
    })
    check_skill_error(result)
    expanded_data = result.get("json") or []
    if not isinstance(expanded_data, list):
        raise HTTPException(500, "AI 返回的展开格式不正确")

    # 计算起始章号 = 前置大纲已展开的章节数总和 + 1
    prev_outlines = (await db.execute(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.chapter_number < outline.chapter_number,
        ).order_by(Outline.chapter_number)
    )).scalars().all()
    start_chapter = 1
    for po in prev_outlines:
        cnt = await db.scalar(select(func.count(Chapter.id)).where(
            Chapter.outline_id == po.id, Chapter.project_id == project_id,
        ))
        start_chapter += (cnt or 0)

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
