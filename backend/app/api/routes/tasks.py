"""通用后台任务路由。

对标 MuMuAINovel 的 tasks.py。提供任务查询/取消/删除/清理入口。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.models.user import User
from app.services import background_task_service as bg

router = APIRouter(prefix="/api/tasks", tags=["后台任务"])


@router.get("")
async def list_tasks(
    project_id: int = Query(None),
    status: str = Query(None),
    task_type: str = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """列出当前用户的任务（活跃优先）。"""
    return await bg.list_user_tasks(
        user_id=user.id,
        project_id=project_id,
        status=status,
        task_type=task_type,
        limit=limit,
    )


@router.get("/active")
async def list_active(
    project_id: int = Query(None),
    user: User = Depends(get_current_user),
):
    """列出活跃任务（pending/running）。"""
    return await bg.list_active_tasks(user_id=user.id, project_id=project_id)


@router.get("/{task_id}")
async def get_task(task_id: int, user: User = Depends(get_current_user)):
    """查询单个任务进度（前端轮询用）。"""
    task = await bg.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["user_id"] != user.id:
        raise HTTPException(403, "无权访问")
    return task


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: int, user: User = Depends(get_current_user)):
    """请求取消任务。"""
    ok = await bg.cancel_task(task_id, user.id)
    if not ok:
        raise HTTPException(404, "任务不存在或无权操作")
    return {"ok": True}


@router.delete("/{task_id}")
async def delete_task(task_id: int, user: User = Depends(get_current_user)):
    """删除已完成的任务记录。"""
    ok = await bg.delete_task(task_id, user.id)
    if not ok:
        raise HTTPException(400, "任务不存在/无权操作/仍在运行")
    return {"ok": True}


@router.post("/{task_id}/retry")
async def retry_task(task_id: int, user: User = Depends(get_current_user)):
    """重试失败的任务：用原 payload 重新提交。"""
    from app.services.async_ai_service import retry_task as do_retry

    try:
        new_id = await do_retry(task_id, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"task_id": new_id}
