"""批量章节生成路由（#12）。

提交批量生成任务 → 后台逐章顺序生成 → 前端轮询进度。
"""
import asyncio
from app.api.routes.projects_pkg.base import *
from app.models.batch_generation_task import BatchGenerationTask
from app.services import batch_generation_service as bgs

router = make_router()


class BatchGenerateReq(BaseModel):
    chapter_ids: list[int]
    enable_analysis: bool = True
    max_retries: int = 2


@router.post("/{project_id}/chapters/batch-generate")
async def batch_generate(
    project_id: int, req: BatchGenerateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """提交批量生成任务。立即返回 task_id，后台逐章生成。"""
    await get_user_project(db, project_id, user)
    if not req.chapter_ids:
        raise HTTPException(400, "请选择至少一个章节")
    # 检查是否已有运行中的批量任务
    active = await bgs.list_active_batch_tasks(user.id, project_id)
    if active:
        raise HTTPException(409, f"已有批量任务进行中（任务 {active[0]['id']}），请等待完成或取消")
    # 创建任务
    task = await bgs.create_batch_task(
        user_id=user.id,
        project_id=project_id,
        chapter_ids=req.chapter_ids,
        enable_analysis=req.enable_analysis,
        max_retries=req.max_retries,
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
