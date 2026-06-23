"""批量章节生成路由（#12）。

提交批量生成任务 → 后台逐章顺序生成 → 前端轮询进度。
支持两种模式：
- 连续模式（推荐）：start_chapter_number + count，自动创建缺失章节并连续生成
- 手动模式（兼容）：chapter_ids，指定具体章节
"""
import asyncio
from app.api.routes.projects_pkg.base import *
from app.models.batch_generation_task import BatchGenerationTask
from app.services import batch_generation_service as bgs

router = make_router()


class BatchGenerateReq(BaseModel):
    # 连续模式（推荐）：从起始章起连续生成 N 章
    start_chapter_number: int | None = None
    count: int | None = None
    # 手动模式（兼容）：指定具体章节 id
    chapter_ids: list[int] = []
    # 通用配置
    enable_analysis: bool = True
    max_retries: int = 2
    target_word_count: int = 3000
    model_override: str = ""       # 指定模型id（空=默认）
    style_id: int | None = None    # 写作风格id（空=项目默认）
    narrative_perspective: str = ""  # 叙事视角（空=按小说设定）

    model_config = {"protected_namespaces": ()}  # 允许 model_* 字段名


async def _resolve_continuous_chapters(db: AsyncSession, project_id: int, start: int, count: int) -> list[int]:
    """连续模式：解析 [start, start+count) 范围内的章节，缺失则从大纲自动创建草稿章。

    返回按章号升序排列的 chapter id 列表。
    """
    from app.models.chapter import Chapter
    from app.models.outline import Outline

    end = start + count  # 不含 end
    # 查范围内已有章节
    existing = (await db.execute(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number >= start,
            Chapter.chapter_number < end,
        )
    )).scalars().all()
    existing_nums = {c.chapter_number for c in existing}

    # 查范围内大纲（用于自动建章的标题/摘要）
    outlines = (await db.execute(
        select(Outline).where(
            Outline.project_id == project_id,
            Outline.chapter_number >= start,
            Outline.chapter_number < end,
        )
    )).scalars().all()
    outline_map = {o.chapter_number: o for o in outlines}

    # 自动创建缺失章
    for ch_num in range(start, end):
        if ch_num not in existing_nums:
            o = outline_map.get(ch_num)
            db.add(Chapter(
                project_id=project_id,
                chapter_number=ch_num,
                title=o.title if o else f"第{ch_num}章",
                summary=(o.summary[:200] if o and o.summary else ""),
                status="draft",
                outline_id=(o.id if o else None),
            ))
    await db.flush()  # 拿到新建章的 id

    # 按章号升序返回 id
    all_in_range = (await db.execute(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.chapter_number >= start,
            Chapter.chapter_number < end,
        ).order_by(Chapter.chapter_number)
    )).scalars().all()
    return [c.id for c in all_in_range]


@router.post("/{project_id}/chapters/batch-generate")
async def batch_generate(
    project_id: int, req: BatchGenerateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """提交批量生成任务。立即返回 task_id，后台逐章生成。

    连续模式：传 start_chapter_number + count（从起始章起连续生成，缺失章自动从大纲创建）。
    手动模式：传 chapter_ids（兼容旧调用）。
    """
    await get_user_project(db, project_id, user)
    # 检查是否已有运行中的批量任务
    active = await bgs.list_active_batch_tasks(user.id, project_id)
    if active:
        raise HTTPException(409, f"已有批量任务进行中（任务 {active[0]['id']}），请等待完成或取消")

    # 解析模式
    if req.start_chapter_number and req.count:
        # 连续模式
        if req.count <= 0 or req.count > 40:
            raise HTTPException(400, "生成数量须在 1-40 之间")
        chapter_ids = await _resolve_continuous_chapters(db, project_id, req.start_chapter_number, req.count)
        await db.commit()
        start_no = req.start_chapter_number
        batch_count = req.count
    elif req.chapter_ids:
        # 手动模式（兼容）
        chapter_ids = req.chapter_ids
        start_no = None
        batch_count = None
    else:
        raise HTTPException(400, "请指定 start_chapter_number+count（连续模式）或 chapter_ids（手动模式）")

    if not chapter_ids:
        raise HTTPException(400, "未解析到待生成的章节")

    # 创建任务
    task = await bgs.create_batch_task(
        user_id=user.id,
        project_id=project_id,
        chapter_ids=chapter_ids,
        enable_analysis=req.enable_analysis,
        max_retries=req.max_retries,
        target_word_count=req.target_word_count,
        model_override=req.model_override,
        style_id=req.style_id,
        narrative_perspective=req.narrative_perspective,
        start_chapter_number=start_no,
        batch_count=batch_count,
        db=db,
    )
    # 后台执行（fire-and-forget）
    asyncio.create_task(bgs.run_batch_generation(task.id))
    return {"task_id": task.id, "total": task.total_chapters, "status": "pending"}


@router.get("/{project_id}/batch-generate/active")
async def get_active_batch(
    project_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """获取当前运行的批量任务（若有）。"""
    await get_user_project(db, project_id, user)
    tasks = await bgs.list_active_batch_tasks(user.id, project_id)
    return tasks[0] if tasks else None


@router.get("/{project_id}/batch-generate/{task_id}/status")
async def batch_status(
    project_id: int, task_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """查询批量任务进度（前端轮询用）。"""
    await get_user_project(db, project_id, user)
    task = await bgs.get_batch_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.post("/{project_id}/batch-generate/{task_id}/cancel")
async def cancel_batch(
    project_id: int, task_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """取消批量生成任务。"""
    await get_user_project(db, project_id, user)
    ok = await bgs.cancel_batch_task(task_id, user.id)
    if not ok:
        raise HTTPException(404, "任务不存在或无权操作")
    return {"ok": True}
