"""章节：CRUD / 生成 / 流式生成 / 重写 / 局部重写 / 清空"""

import json
from datetime import datetime, timedelta

from app.api.routes.projects_pkg.base import *
from app.core.database import async_session
from app.models.background_task import BackgroundTask
from app.services import background_task_service as bg_service
from app.services.async_ai_service import submit_async_task

router = make_router()


async def _refresh_project_word_count(db: AsyncSession, project_id: int):
    """汇总项目所有章节字数，更新 project.current_word_count。"""
    total = (
        await db.execute(
            select(func.coalesce(func.sum(Chapter.word_count), 0)).where(
                Chapter.project_id == project_id
            )
        )
    ).scalar() or 0
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj:
        proj.current_word_count = total
        await db.commit()


async def _check_prev_analyzed(
    db: AsyncSession, project_id: int, chapter_number: int
) -> Optional[str]:
    """检查前一章是否已分析。返回错误消息（需阻止时），None 表示通过。

    规则：前一章有内容（>=50字）但未分析时，阻止后续生成和分析。
    """
    prev = (
        (
            await db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number < chapter_number,
                )
                .order_by(Chapter.chapter_number.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if not prev:
        return None  # 没有前一章
    if not prev.content or (prev.word_count or 0) < 50:
        return None  # 前一章没有实质内容，由 word_count gate 处理
    # 前一章有内容 → 必须已分析
    prev_analyzed = (
        (
            await db.execute(
                select(PlotAnalysis.chapter_id).where(PlotAnalysis.chapter_id == prev.id)
            )
        )
        .scalars()
        .first()
    )
    if not prev_analyzed:
        return f"请先分析第{prev.chapter_number}章，再操作后续章节"
    return None


@router.post("/{project_id}/chapters")
async def create_chapter(
    project_id: int,
    req: ChapterCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
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
async def list_chapters(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    await get_user_project(db, project_id, user)  # 权限校验
    result = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
    )
    chapters = result.scalars().all()
    # 批量查询已分析章节 id 集合（避免 N+1）
    analyzed_ids = set(
        (
            await db.execute(
                select(PlotAnalysis.chapter_id).where(PlotAnalysis.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "chapter_number": c.chapter_number,
            "title": c.title,
            "word_count": c.word_count,
            "status": c.status,
            "quality_score": c.quality_score,
            "summary": c.summary[:100] if c.summary else "",
            "content_preview": (c.content[:150] if c.content else ""),
            "outline_id": c.outline_id,
            "sub_index": c.sub_index or 1,
            "generation_mode": c.generation_mode or "one_to_one",
            "has_expansion_plan": bool(c.expansion_plan),
            "analyzed": c.id in analyzed_ids,
        }
        for c in chapters
    ]


@router.get("/{project_id}/chapters/{chapter_id}")
async def get_chapter(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    return {
        "id": c.id,
        "chapter_number": c.chapter_number,
        "title": c.title,
        "content": c.content,
        "word_count": c.word_count,
        "status": c.status,
        "summary": c.summary,
        "quality_score": c.quality_score,
        "quality_detail": c.quality_detail,
        "outline_id": c.outline_id,
        "sub_index": c.sub_index or 1,
        "generation_mode": c.generation_mode or "one_to_one",
        "expansion_plan": c.expansion_plan,
        "raw_output": c.raw_output or "",
    }


@router.put("/{project_id}/chapters/{chapter_id}")
async def update_chapter(
    project_id: int,
    chapter_id: int,
    req: ChapterUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    data = req.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(c, key, value)
    if "content" in data:
        c.word_count = len(data["content"] or "")
    await db.commit()
    if "content" in data:
        await _refresh_project_word_count(db, project_id)
    return {"ok": True}


@router.delete("/{project_id}/chapters/{chapter_id}")
async def delete_chapter(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    await db.delete(c)
    await db.commit()
    await _refresh_project_word_count(db, project_id)
    return {"ok": True}


@router.post("/{project_id}/chapters/{chapter_id}/generate")
async def generate_chapter(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    # 检查前一章是否已分析
    block_msg = await _check_prev_analyzed(db, project_id, c.chapter_number)
    if block_msg:
        raise HTTPException(409, block_msg)
    service = ChapterService(db, project_id, user.id)
    result = await service.generate_chapter(chapter_id)
    if result.get("error"):
        raise HTTPException(500, result["error"])
    await _refresh_project_word_count(db, project_id)
    return result


@router.post("/{project_id}/chapters/{chapter_id}/generate-async")
async def generate_chapter_async(
    project_id: int,
    chapter_id: int,
    req: dict = {},
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步生成章节：立即返回 task_id，后台执行。可选 body: {skill_name} 注入自定义提示词。"""
    await get_user_project(db, project_id, user)
    ch = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "章节不存在")
    block_msg = await _check_prev_analyzed(db, project_id, ch.chapter_number)
    if block_msg:
        raise HTTPException(409, block_msg)

    from app.services.async_ai_service import submit_async_task

    skill_name = req.get("skill_name") if isinstance(req, dict) else None
    overrides = {}
    if skill_name:
        overrides["skill_name"] = skill_name
    has_style = False
    for k in (
        "style_config",
        "style_name",
        "style_custom_prompt",
        "style_traits",
        "style_reference_text",
    ):
        v = req.get(k) if isinstance(req, dict) else None
        if v:
            overrides[k] = v
            has_style = True

    # 叙事视角 / 目标字数 / 模型 / 思考模式覆盖（空值=按小说设定/账户默认）
    if isinstance(req, dict):
        if req.get("narrative_pov"):
            overrides["narrative_pov"] = req["narrative_pov"]
        if req.get("target_word_count"):
            overrides["target_word_count"] = req["target_word_count"]
        if req.get("model"):
            overrides["model"] = req["model"]
        if req.get("thinking_mode"):
            overrides["thinking_mode"] = req["thinking_mode"]

    # 未传写作风格时，自动加载用户默认风格
    if not has_style:
        try:
            from app.models.writing_style import WritingStyle

            default_ws = (
                await db.execute(
                    select(WritingStyle).where(
                        WritingStyle.user_id == user.id,
                        WritingStyle.is_default == True,
                    )
                )
            ).scalar_one_or_none()
            if default_ws:
                if default_ws.config:
                    overrides["style_config"] = default_ws.config
                if default_ws.name:
                    overrides["style_name"] = default_ws.name
                if default_ws.custom_prompt:
                    overrides["style_custom_prompt"] = default_ws.custom_prompt
                if default_ws.style_traits:
                    overrides["style_traits"] = default_ws.style_traits
                if default_ws.reference_text:
                    overrides["style_reference_text"] = default_ws.reference_text
        except Exception:
            pass

    async def _run_chapter(task_id: int, payload: dict, db: AsyncSession):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id, db=db)
        if await tracker.is_cancelled():
            await tracker.cancel("用户取消")
            return
        await tracker.update(
            stage="preparing", message=f"准备生成第{payload['chapter_number']}章..."
        )
        service = ChapterService(db, payload["project_id"], payload["user_id"])
        await tracker.update(
            stage="generating", message=f"AI 正在生成第{payload['chapter_number']}章..."
        )
        result = await service.generate_chapter(
            payload["chapter_id"], overrides=payload.get("overrides")
        )
        if result.get("error"):
            await tracker.fail(result["error"])
            return
        await _refresh_project_word_count(db, payload["project_id"])
        await tracker.complete(
            result=result,
            message=f"第{payload['chapter_number']}章生成完成（{result.get('word_count', 0)}字）",
        )

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="chapter_generate",
        title=f"生成第{ch.chapter_number}章",
        payload={
            "chapter_id": chapter_id,
            "project_id": project_id,
            "user_id": user.id,
            "chapter_number": ch.chapter_number,
            "overrides": overrides,
        },
        runner=_run_chapter,
    )
    return {"task_id": task_id, "chapter_id": chapter_id}


@router.post("/{project_id}/chapters/batch-generate-range")
async def batch_generate_chapters(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
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
        chapter = (
            await db.execute(
                select(Chapter).where(
                    Chapter.project_id == project_id, Chapter.chapter_number == chapter_number
                )
            )
        ).scalar_one_or_none()
        if not chapter:
            # 从大纲创建草稿章节
            chapter = Chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=f"第{chapter_number}章",
                status="draft",
            )
            db.add(chapter)
            await db.commit()
            await db.refresh(chapter)
        elif chapter.status == "completed" and chapter.content:
            results.append(
                {"chapter_number": chapter_number, "status": "skipped", "reason": "已有内容"}
            )
            continue

        try:
            service = ChapterService(db, project_id, user.id)
            result = await service.generate_chapter(chapter.id)
            if result.get("error"):
                results.append(
                    {
                        "chapter_number": chapter_number,
                        "status": "failed",
                        "error": result["error"][:100],
                    }
                )
            else:
                results.append(
                    {
                        "chapter_number": chapter_number,
                        "status": "success",
                        "word_count": result.get("word_count", 0),
                    }
                )
        except Exception as e:
            results.append(
                {"chapter_number": chapter_number, "status": "failed", "error": str(e)[:100]}
            )

    success_count = sum(1 for r in results if r["status"] == "success")
    return {"results": results, "total": len(results), "success": success_count}


@router.post("/{project_id}/chapters/{chapter_id}/clear")
async def clear_chapter(
    project_id: int,
    chapter_id: int,
    cascade: bool = False,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    service = ChapterService(db, project_id, user.id)
    chapter, cleared = await service.clear_chapter_content(chapter_id, cascade=cascade)
    return {"ok": True, "chapter_id": chapter.id, "cleared": cleared}


# ===== 章节剧情分析（异步后台任务，对标 MuMu POST /chapters/{id}/analyze）=====

# 分析任务卡死自恢复阈值
_ANALYZE_RUNNING_TIMEOUT = timedelta(minutes=3)
_ANALYZE_PENDING_TIMEOUT = timedelta(minutes=3)


async def _get_latest_analyze_task(db: AsyncSession, chapter_id: int) -> Optional[BackgroundTask]:
    """查该章节最新的 chapter_analyze 类型任务。

    SQLite 下 JSON 路径查询不可靠，改为取最近若干条同类型任务后在 Python 层匹配 payload.chapter_id。
    """
    rows = (
        (
            await db.execute(
                select(BackgroundTask)
                .where(BackgroundTask.task_type == "chapter_analyze")
                .order_by(BackgroundTask.id.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for t in rows:
        if (t.payload or {}).get("chapter_id") == chapter_id:
            return t
    return None


async def _run_chapter_analysis(task_id: int, payload: dict, db: AsyncSession):
    """分析任务后台执行协程（共享 session）。

    复用 ChapterService._auto_analyze，通过 on_progress 回调上报进度到 BackgroundTask。
    """
    tracker = bg_service.TaskProgressTracker(task_id, db=db)

    async def on_progress(progress: int, message: str):
        await tracker.update(progress=progress, message=message)

    chapter_id = payload["chapter_id"]
    project_id = payload["project_id"]
    user_id = payload["user_id"]
    # 重新校验权限（后台共享 session）
    proj = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if not proj or proj.user_id != user_id:
        await tracker.fail("项目不存在或无权访问")
        return

    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        await tracker.fail("章节不存在")
        return
    if not c.content or len(c.content.strip()) < 50:
        await tracker.fail("章节内容过少，无法分析")
        return

    # 删除旧分析（避免重复）
    old_analyses = (
        (
            await db.execute(
                select(PlotAnalysis).where(PlotAnalysis.chapter_id == chapter_id)
            )
        )
        .scalars()
        .all()
    )
    for old in old_analyses:
        await db.delete(old)
    await db.commit()

    await tracker.update(
        stage="analyzing", progress=3, message=f"正在分析第{c.chapter_number}章..."
    )

    service = ChapterService(db, project_id, user_id)
    try:
        await service._auto_analyze(c, on_progress=on_progress)
        await tracker.complete(
            result={"chapter_id": chapter_id, "chapter_number": c.chapter_number},
            message=f"第{c.chapter_number}章分析完成",
        )
    except Exception as e:
        await tracker.fail(f"分析失败: {str(e)[:500]}")


@router.post("/{project_id}/chapters/{chapter_id}/analyze")
async def trigger_analysis(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步触发章节剧情分析。

    立即创建后台任务返回 task_id，前端通过右下角任务面板或 status 接口轮询进度。
    幂等：若该章节已有 pending/running 的分析任务，直接返回旧 task_id，不重复创建。
    """
    await get_user_project(db, project_id, user)
    c = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "章节不存在")
    if not c.content or len(c.content.strip()) < 50:
        raise HTTPException(400, "章节内容过少，无法分析")

    # 幂等去重：已有 pending/running 任务则复用
    existing = await _get_latest_analyze_task(db, chapter_id)
    if existing and existing.status in ("pending", "running"):
        return {
            "task_id": existing.id,
            "chapter_id": chapter_id,
            "status": existing.status,
            "message": "该章节已有分析任务在进行中",
        }

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="chapter_analyze",
        title=f"分析第{c.chapter_number}章",
        payload={
            "chapter_id": chapter_id,
            "project_id": project_id,
            "user_id": user.id,
            "chapter_number": c.chapter_number,
        },
        runner=_run_chapter_analysis,
    )
    return {
        "task_id": task_id,
        "chapter_id": chapter_id,
        "status": "pending",
        "message": "分析任务已提交",
    }


@router.get("/{project_id}/chapters/{chapter_id}/analyze/status")
async def get_analysis_status(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """查询章节分析任务状态（前端轮询用，对标 MuMu analysis/status）。

    含卡死自恢复：running 超 3 分钟 / pending 超 3 分钟自动标记 failed。
    返回字段对齐 MuMu：{has_task, task_id, status, progress, error_message, auto_recovered, ...}
    """
    await get_user_project(db, project_id, user)
    task = await _get_latest_analyze_task(db, chapter_id)
    if not task:
        return {
            "has_task": False,
            "task_id": None,
            "chapter_id": chapter_id,
            "status": "none",
            "progress": 0,
            "error_message": None,
            "auto_recovered": False,
            "created_at": None,
            "started_at": None,
            "completed_at": None,
        }

    auto_recovered = False
    now = datetime.utcnow()
    # 卡死自恢复（懒触发）
    if (
        task.status == "running"
        and task.started_at
        and now - task.started_at > _ANALYZE_RUNNING_TIMEOUT
    ):
        task.status = "failed"
        task.error_message = "分析任务超时（运行超过3分钟未完成），已自动恢复"
        task.completed_at = now
        task.updated_at = now
        auto_recovered = True
        await db.commit()
    elif (
        task.status == "pending"
        and task.created_at
        and now - task.created_at > _ANALYZE_PENDING_TIMEOUT
    ):
        task.status = "failed"
        task.error_message = "分析任务排队超时（超过3分钟未启动），已自动恢复"
        task.completed_at = now
        task.updated_at = now
        auto_recovered = True
        await db.commit()

    return {
        "has_task": True,
        "task_id": task.id,
        "chapter_id": chapter_id,
        "status": task.status,
        "progress": task.progress or 0,
        "error_message": task.error,
        "auto_recovered": auto_recovered,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


async def _run_batch_analysis(task_id: int, payload: dict, db: AsyncSession):
    """批量分析后台执行协程：逐章串行分析，逐章上报进度。"""
    tracker = bg_service.TaskProgressTracker(task_id, db=db)
    project_id = payload["project_id"]
    user_id = payload["user_id"]
    chapter_ids: list[int] = payload.get("chapter_ids", [])

    service = ChapterService(db, project_id, user_id)
    total = len(chapter_ids)
    completed = 0
    failed = []
    for i, chapter_id in enumerate(chapter_ids):
        if await tracker.is_cancelled():
            await tracker.update(message="批量分析已取消")
            return
        c = (
            await db.execute(
                select(Chapter).where(
                    Chapter.id == chapter_id, Chapter.project_id == project_id
                )
            )
        ).scalar_one_or_none()
        if not c:
            continue
        await tracker.update(
            progress=int(5 + (i / max(total, 1)) * 90),
            message=f"正在分析第{c.chapter_number}章（{i + 1}/{total}）...",
        )
        try:
            # 删除旧分析
            olds = (
                (
                    await db.execute(
                        select(PlotAnalysis).where(PlotAnalysis.chapter_id == chapter_id)
                    )
                )
                .scalars()
                .all()
            )
            for o in olds:
                await db.delete(o)
            await db.commit()
            await service._auto_analyze(c)
            completed += 1
        except Exception as e:
            failed.append({"chapter_number": c.chapter_number, "error": str(e)[:200]})

    await tracker.complete(
        result={"analyzed": completed, "failed": failed, "total": total},
        message=f"批量分析完成：成功 {completed} 章"
        + (f"，失败 {len(failed)} 章" if failed else ""),
    )


@router.post("/{project_id}/chapters/analyze-all")
async def analyze_all_unanalyzed(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步批量分析所有未分析的章节（对标 MuMu 一键分析）。

    立即创建后台任务返回 task_id，逐章串行分析并上报进度。
    """
    await get_user_project(db, project_id, user)
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
    # 筛选「有内容 + 未分析」的章节
    candidate_ids = []
    for c in chapters:
        if not c.content or len(c.content.strip()) < 50:
            continue
        existing = (
            (await db.execute(select(PlotAnalysis).where(PlotAnalysis.chapter_id == c.id)))
            .scalars()
            .first()
        )
        if not existing:
            candidate_ids.append(c.id)

    if not candidate_ids:
        return {
            "task_id": None,
            "analyzed": 0,
            "failed": [],
            "total_chapters": len(chapters),
            "message": "没有需要分析的章节",
        }

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="chapter_batch_analyze",
        title=f"批量分析 {len(candidate_ids)} 章",
        payload={
            "project_id": project_id,
            "user_id": user.id,
            "chapter_ids": candidate_ids,
            "total": len(candidate_ids),
        },
        runner=_run_batch_analysis,
    )
    return {
        "task_id": task_id,
        "total": len(candidate_ids),
        "total_chapters": len(chapters),
        "status": "pending",
        "message": "批量分析任务已提交",
    }


# ===== 章节导航（对标 MuMu /chapters/{id}/navigation）=====
@router.get("/{project_id}/chapters/{chapter_id}/navigation")
async def get_chapter_navigation(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """章节导航：返回当前章及前后章（按 chapter_number 升序）。"""
    await get_user_project(db, project_id, user)
    current = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not current:
        raise HTTPException(404, "章节不存在")

    def _mini(ch: Optional[Chapter]):
        if not ch:
            return None
        return {"id": ch.id, "chapter_number": ch.chapter_number, "title": ch.title or ""}

    prev = (
        (
            await db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number < current.chapter_number,
                )
                .order_by(Chapter.chapter_number.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    nxt = (
        (
            await db.execute(
                select(Chapter)
                .where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_number > current.chapter_number,
                )
                .order_by(Chapter.chapter_number.asc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    return {"current": _mini(current), "previous": _mini(prev), "next": _mini(nxt)}


@router.post("/{project_id}/chapters/{chapter_id}/regenerate")
async def regenerate_chapter(
    project_id: int,
    chapter_id: int,
    req: ChapterRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """章节重写：根据修改要求和质量分析重写全章"""
    proj = await get_user_project(db, project_id, user)
    chapter = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")

    ai_analysis = ""
    if req.include_analysis:
        analysis = (
            (
                await db.execute(
                    select(PlotAnalysis)
                    .where(
                        PlotAnalysis.project_id == project_id,
                        PlotAnalysis.chapter_number == chapter.chapter_number,
                    )
                    .order_by(PlotAnalysis.id.desc())
                )
            )
            .scalars()
            .first()
        )
        if analysis:
            ai_analysis = json.dumps(
                {"suggestions": analysis.suggestions, "quality_scores": analysis.quality_scores},
                ensure_ascii=False,
            )

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
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    outline_info = (
        "\n".join(
            [
                f"第{o.chapter_number}章 {o.title}: {o.summary}"
                for o in outlines
                if o.chapter_number == chapter.chapter_number
            ]
        )
        or "暂无"
    )
    # 使用章节前的历史角色状态，避免未来信息泄露
    from app.api.routes.projects_pkg.characters import get_character_state_at_chapter

    char_lines = []
    for c in chars:
        snapshot = await get_character_state_at_chapter(
            db, project_id, c.id, chapter.chapter_number
        )
        s = snapshot if snapshot else {}
        personality = str(s.get("personality", c.personality))[:100]
        status = str(s.get("status", c.status))
        mental = str(s.get("mental_state", c.mental_state))[:40]
        extra = ""
        if status and status != "alive":
            extra += f" 状态:{status}"
        if mental:
            extra += f" 心理:{mental}"
        char_lines.append(f"- {c.name}({c.role}){extra}: {personality}")
    characters_info = "\n".join(char_lines) or "暂无"
    style_str = (
        json.dumps(proj.writing_style or {}, ensure_ascii=False) if proj.writing_style else ""
    )

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "chapter_regeneration_system",
        ai_client,
        {
            "chapter_content": chapter.content or "",
            "chapter_number": str(chapter.chapter_number),
            "chapter_title": chapter.title or "",
            "modification_requirements": req.instructions,
            "ai_analysis": ai_analysis or "无",
            "outline_info": outline_info,
            "characters_info": characters_info,
            "writing_style": style_str,
            "genre": proj.genre or "网文",
            "narrative_pov": proj.narrative_pov or "第三人称",
            "user_prompt": f"请重写第{chapter.chapter_number}章「{chapter.title}」。修改要求：{req.instructions or '综合质量分析建议进行优化'}",
        },
    )
    check_skill_error(result)

    new_content = (result.get("json") or {}).get("content", "") or result.get("content", "")
    if not new_content:
        raise HTTPException(500, "AI 未返回重写内容")
    chapter.content = new_content
    chapter.word_count = len(new_content)
    await db.commit()
    return {"chapter_id": chapter.id, "content": new_content, "word_count": len(new_content)}


@router.post("/{project_id}/chapters/{chapter_id}/regenerate/stream")
async def regenerate_chapter_stream(
    project_id: int,
    chapter_id: int,
    req: ChapterRegenerateRequest,
    user=Depends(get_current_user),
):
    """章节重写 —— SSE 流式版（通用 sse_wrap 包装，防 524 超时）。"""
    from app.core.database import async_session as _async_session

    async def _do():
        async with _async_session() as db:
            return await regenerate_chapter(project_id, chapter_id, req, db, user)

    return await sse_wrap(_do())


@router.post("/{project_id}/chapters/{chapter_id}/partial-regenerate")
async def partial_regenerate_chapter(
    project_id: int,
    chapter_id: int,
    req: PartialRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """局部重写：仅重写选中的文本段落"""
    await get_user_project(db, project_id, user)
    # 没传上下文时自动从章节内容提取
    if not req.context_before and not req.context_after:
        chapter = (
            await db.execute(
                select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
            )
        ).scalar_one_or_none()
        if chapter and chapter.content:
            idx = chapter.content.find(req.selected_text)
            if idx >= 0:
                req.context_before = chapter.content[max(0, idx - 500) : idx]
                req.context_after = chapter.content[
                    idx + len(req.selected_text) : idx + len(req.selected_text) + 500
                ]

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "partial_regenerate",
        ai_client,
        {
            "original_text": req.selected_text,
            "before_text": req.context_before,
            "after_text": req.context_after,
            "modification_requirements": req.user_instructions,
            "length_requirement": req.length_requirement or "保持原字数",
            "user_prompt": f"请重写以下文本段落。修改要求：{req.user_instructions}",
        },
    )
    check_skill_error(result)
    rewritten = (result.get("json") or {}).get("rewritten_text", "") or result.get("content", "")
    return {"rewritten_text": rewritten}


@router.post("/{project_id}/chapters/{chapter_id}/partial-regenerate/stream")
async def partial_regenerate_chapter_stream(
    project_id: int,
    chapter_id: int,
    req: PartialRegenerateRequest,
    user=Depends(get_current_user),
):
    """局部重写 —— SSE 流式版（通用 sse_wrap 包装，防 524 超时）。"""
    from app.core.database import async_session as _async_session

    async def _do():
        async with _async_session() as db:
            return await partial_regenerate_chapter(project_id, chapter_id, req, db, user)

    return await sse_wrap(_do())


@router.post("/{project_id}/chapters/cleanup-duplicate-analyses")
async def cleanup_duplicate_analyses(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """清理重复的 PlotAnalysis 记录（每个章节只保留最新一条）"""
    await get_user_project(db, project_id, user)
    service = ChapterService(db, project_id, user.id)
    deleted = await service.cleanup_duplicate_analyses()
    return {"ok": True, "deleted": deleted}
