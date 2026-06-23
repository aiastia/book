"""异步 AI 任务执行服务。

将同步的 AI 操作（章节生成、大纲生成、角色生成等）包装为异步后台任务，
用户提交后立即返回 task_id，不阻塞前端。

设计模式：
1. 路由层创建 BackgroundTask 记录，返回 task_id
2. asyncio.create_task 在后台执行实际 AI 调用
3. 前端通过 /api/tasks/{task_id} 轮询进度
4. 复用现有 BackgroundTask 队列 + InitTaskFloat 浮窗

使用示例（在路由层）：
    task_id = await submit_async_task(
        user_id, project_id, "chapter_generate", "生成章节",
        payload={"chapter_id": 123},
        runner=run_chapter_generation,
    )
    return {"task_id": task_id}
"""
import asyncio
from typing import Callable, Optional
from app.services import background_task_service as bg_service


async def submit_async_task(
    user_id: int,
    project_id: int,
    task_type: str,
    title: str,
    payload: dict,
    runner: Callable,
) -> int:
    """提交一个异步 AI 任务。

    Args:
        user_id: 用户ID
        project_id: 项目ID
        task_type: 任务类型（chapter_generate / outline_new / outline_continue / characters_batch 等）
        title: 任务标题（显示在浮窗）
        payload: 任务参数（传给 runner 的数据快照）
        runner: 异步执行函数 async def runner(task_id: int, payload: dict)

    Returns:
        task_id: 任务ID，前端用于轮询
    """
    task = await bg_service.create_task(
        user_id=user_id,
        project_id=project_id,
        task_type=task_type,
        title=title,
        payload=payload,
    )
    asyncio.create_task(_wrap_runner(task.id, runner, payload))
    return task.id


async def _wrap_runner(task_id: int, runner: Callable, payload: dict):
    """包装 runner：标记开始、执行、标记完成/失败。"""
    await bg_service.mark_started(task_id)
    try:
        await runner(task_id, payload)
    except Exception as e:
        tracker = bg_service.TaskProgressTracker(task_id)
        await tracker.fail(str(e)[:5000])
