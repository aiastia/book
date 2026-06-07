"""章节：CRUD / 生成 / 流式生成 / 重写 / 局部重写 / 清空"""
import json
from app.api.routes.projects_pkg.base import *


router = make_router()


@router.post("/{project_id}/chapters")
async def create_chapter(project_id: int, req: ChapterCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    chapter = Chapter(project_id=project_id, **req.model_dump())
    if chapter.content:
        chapter.word_count = len(chapter.content)
        chapter.status = "completed"
    db.add(chapter)
    await db.commit()
    await db.refresh(chapter)
    return {"id": chapter.id, "chapter_number": chapter.chapter_number}


@router.get("/{project_id}/chapters")
async def list_chapters(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    result = await db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number))
    return [{
        "id": c.id, "chapter_number": c.chapter_number, "title": c.title,
        "word_count": c.word_count, "status": c.status, "quality_score": c.quality_score,
        "summary": c.summary[:100] if c.summary else "",
        "outline_id": c.outline_id, "sub_index": c.sub_index or 1,
        "generation_mode": c.generation_mode or "one_to_one",
    } for c in result.scalars().all()]


@router.get("/{project_id}/chapters/{chapter_id}")
async def get_chapter(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    return {
        "id": c.id, "chapter_number": c.chapter_number, "title": c.title,
        "content": c.content, "word_count": c.word_count, "status": c.status,
        "summary": c.summary, "quality_score": c.quality_score, "quality_detail": c.quality_detail,
        "outline_id": c.outline_id, "sub_index": c.sub_index or 1,
        "generation_mode": c.generation_mode or "one_to_one",
        "expansion_plan": c.expansion_plan,
    }


@router.put("/{project_id}/chapters/{chapter_id}")
async def update_chapter(project_id: int, chapter_id: int, req: ChapterUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    data = req.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(c, key, value)
    if "content" in data:
        c.word_count = len(data["content"] or "")
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/chapters/{chapter_id}")
async def delete_chapter(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/chapters/{chapter_id}/generate")
async def generate_chapter(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    service = ChapterService(db, project_id, user.id)
    result = await service.generate_chapter(chapter_id)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return result


@router.post("/{project_id}/chapters/{chapter_id}/generate-stream")
async def generate_chapter_stream(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    service = ChapterService(db, project_id, user.id)

    async def event_generator():
        async for chunk in service.generate_chapter_stream(chapter_id):
            yield f"data: {chunk}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{project_id}/chapters/batch-generate-range")
async def batch_generate_chapters(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """批量生成章节（按章节号范围，同步阻塞版）。

    req: { start: 起始章号, end: 结束章号 }
    每章生成后自动进行摘要+剧情分析，失败则跳过继续。
    注意：这是同步阻塞接口。推荐使用 /chapters/batch-generate（异步后台，#12）。
    """
    await get_user_project(db, project_id, user)
    start = int(req.get("start", 1))
    end = int(req.get("end", start))
    if end < start:
        raise HTTPException(400, "结束章号不能小于起始章号")
    if end - start > 20:
        raise HTTPException(400, "单次批量生成不超过 20 章")

    results = []
    for chapter_number in range(start, end + 1):
        # 找到或创建该章
        chapter = (await db.execute(
            select(Chapter).where(Chapter.project_id == project_id, Chapter.chapter_number == chapter_number)
        )).scalar_one_or_none()
        if not chapter:
            # 从大纲创建草稿章节
            chapter = Chapter(project_id=project_id, chapter_number=chapter_number, title=f"第{chapter_number}章", status="draft")
            db.add(chapter)
            await db.commit()
            await db.refresh(chapter)
        elif chapter.status == "completed" and chapter.content:
            results.append({"chapter_number": chapter_number, "status": "skipped", "reason": "已有内容"})
            continue

        try:
            service = ChapterService(db, project_id, user.id)
            result = await service.generate_chapter(chapter.id)
            if result.get("error"):
                results.append({"chapter_number": chapter_number, "status": "failed", "error": result["error"][:100]})
            else:
                results.append({"chapter_number": chapter_number, "status": "success", "word_count": result.get("word_count", 0)})
        except Exception as e:
            results.append({"chapter_number": chapter_number, "status": "failed", "error": str(e)[:100]})

    success_count = sum(1 for r in results if r["status"] == "success")
    return {"results": results, "total": len(results), "success": success_count}


@router.post("/{project_id}/chapters/{chapter_id}/clear")
async def clear_chapter(project_id: int, chapter_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    service = ChapterService(db, project_id, user.id)
    chapter = await service.clear_chapter_content(chapter_id)
    return {"ok": True, "chapter_id": chapter.id}


# ===== 手动触发剧情分析（对标 MuMu POST /chapters/{id}/analyze）=====
@router.post("/{project_id}/chapters/{chapter_id}/analyze")
async def trigger_analysis(
    project_id: int, chapter_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """手动触发章节剧情分析。复用 ChapterService._auto_analyze 逻辑。

    适用场景：自动分析失败、老章节未分析、想重新分析。
    """
    await get_user_project(db, project_id, user)
    c = (await db.execute(
        select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    if not c.content or len(c.content.strip()) < 50:
        raise HTTPException(400, "章节内容过少，无法分析")

    # 删除旧分析（避免重复）
    old_analyses = (await db.execute(
        select(PlotAnalysis).where(PlotAnalysis.chapter_id == chapter_id)
    )).scalars().all()
    for old in old_analyses:
        await db.delete(old)
    await db.commit()

    service = ChapterService(db, project_id, user.id)
    try:
        await service._auto_analyze(c)
    except Exception as e:
        raise HTTPException(500, f"分析失败: {str(e)}")

    # 返回新分析
    analysis = (await db.execute(
        select(PlotAnalysis).where(PlotAnalysis.chapter_id == chapter_id).order_by(PlotAnalysis.id.desc())
    )).scalars().first()
    if not analysis:
        raise HTTPException(500, "分析未产生结果（AI 可能返回了非 JSON 格式），请重试")
    return {
        "ok": True,
        "analysis": {
            "id": analysis.id,
            "chapter_number": analysis.chapter_number,
            "plot_stage": analysis.plot_stage or "",
            "hooks": analysis.hooks,
            "foreshadows": analysis.foreshadows,
            "conflicts": analysis.conflicts,
            "conflict_types": analysis.conflict_types or [],
            "emotional_curve": analysis.emotional_curve or {},
            "character_states": analysis.character_states,
            "organization_states": analysis.organization_states or [],
            "key_plot_points": analysis.key_plot_points,
            "pacing": analysis.pacing or "",
            "dialogue_ratio": analysis.dialogue_ratio or 0,
            "description_ratio": analysis.description_ratio or 0,
            "quality_scores": analysis.quality_scores,
            "suggestions": analysis.suggestions,
        },
    }


@router.post("/{project_id}/chapters/analyze-all")
async def analyze_all_unanalyzed(
    project_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """批量分析所有未分析的章节（对标 MuMu 一键分析）。"""
    await get_user_project(db, project_id, user)
    chapters = (await db.execute(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
    )).scalars().all()
    service = ChapterService(db, project_id, user.id)
    analyzed = 0
    failed = []
    for c in chapters:
        if not c.content or len(c.content.strip()) < 50:
            continue
        existing = (await db.execute(
            select(PlotAnalysis).where(PlotAnalysis.chapter_id == c.id)
        )).scalars().first()
        if existing:
            continue
        try:
            await service._auto_analyze(c)
            analyzed += 1
        except Exception as e:
            failed.append({"chapter_number": c.chapter_number, "error": str(e)[:200]})
    return {"analyzed": analyzed, "failed": failed, "total_chapters": len(chapters)}


@router.post("/{project_id}/chapters/{chapter_id}/regenerate")
async def regenerate_chapter(project_id: int, chapter_id: int, req: ChapterRegenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """章节重写：根据修改要求和质量分析重写全章"""
    proj = await get_user_project(db, project_id, user)
    chapter = (await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")

    ai_analysis = ""
    if req.include_analysis:
        analysis = (await db.execute(select(PlotAnalysis).where(PlotAnalysis.project_id == project_id, PlotAnalysis.chapter_number == chapter.chapter_number).order_by(PlotAnalysis.id.desc()))).scalars().first()
        if analysis:
            ai_analysis = json.dumps({"suggestions": analysis.suggestions, "quality_scores": analysis.quality_scores}, ensure_ascii=False)

    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    outline_info = "\n".join([f"第{o.chapter_number}章 {o.title}: {o.summary}" for o in outlines if o.chapter_number == chapter.chapter_number]) or "暂无"
    characters_info = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    style_str = json.dumps(proj.writing_style or {}, ensure_ascii=False) if proj.writing_style else ""

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("chapter_regeneration_system", ai_client, {
        "chapter_content": chapter.content or "", "chapter_number": str(chapter.chapter_number),
        "chapter_title": chapter.title or "", "modification_requirements": req.instructions,
        "ai_analysis": ai_analysis or "无", "outline_info": outline_info,
        "characters_info": characters_info, "writing_style": style_str,
        "genre": proj.genre or "网文", "narrative_pov": proj.narrative_pov or "第三人称",
        "user_prompt": f"请重写第{chapter.chapter_number}章「{chapter.title}」。修改要求：{req.instructions or '综合质量分析建议进行优化'}",
    })
    check_skill_error(result)

    new_content = (result.get("json") or {}).get("content", "") or result.get("content", "")
    if not new_content:
        raise HTTPException(500, "AI 未返回重写内容")
    chapter.content = new_content
    chapter.word_count = len(new_content)
    await db.commit()
    return {"chapter_id": chapter.id, "content": new_content, "word_count": len(new_content)}


@router.post("/{project_id}/chapters/{chapter_id}/partial-regenerate")
async def partial_regenerate_chapter(project_id: int, chapter_id: int, req: PartialRegenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """局部重写：仅重写选中的文本段落"""
    await get_user_project(db, project_id, user)
    # 没传上下文时自动从章节内容提取
    if not req.context_before and not req.context_after:
        chapter = (await db.execute(select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id))).scalar_one_or_none()
        if chapter and chapter.content:
            idx = chapter.content.find(req.selected_text)
            if idx >= 0:
                req.context_before = chapter.content[max(0, idx - 500):idx]
                req.context_after = chapter.content[idx + len(req.selected_text):idx + len(req.selected_text) + 500]

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("partial_regenerate", ai_client, {
        "original_text": req.selected_text, "before_text": req.context_before,
        "after_text": req.context_after, "modification_requirements": req.user_instructions,
        "length_requirement": req.length_requirement or "保持原字数",
        "user_prompt": f"请重写以下文本段落。修改要求：{req.user_instructions}",
    })
    check_skill_error(result)
    rewritten = (result.get("json") or {}).get("rewritten_text", "") or result.get("content", "")
    return {"rewritten_text": rewritten}
