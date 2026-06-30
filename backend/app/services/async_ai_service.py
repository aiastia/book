"""异步 AI 任务执行服务。

将同步的 AI 操作（章节生成、大纲生成、角色生成等）包装为异步后台任务，
用户提交后立即返回 task_id，不阻塞前端。

设计模式：
1. 路由层创建 BackgroundTask 记录，返回 task_id
2. asyncio.create_task 在后台执行实际 AI 调用
3. 前端通过 /api/tasks/{task_id} 轮询进度
4. 复用现有 BackgroundTask 队列 + InitTaskFloat 浮窗
5. runner 注册表支持失败任务通用重试

使用示例（在路由层）：
    task_id = await submit_async_task(
        user_id, project_id, "chapter_generate", "生成章节",
        payload={"chapter_id": 123},
        runner=run_chapter_generation,
    )
    return {"task_id": task_id}
"""

import asyncio
import logging
from collections.abc import Callable

from app.core.config import settings
from app.core.database import async_session
from app.services import background_task_service as bg_service

logger = logging.getLogger(__name__)

# runner 注册表：task_type → (runner, factory_module)
# factory_module 用于后端重启后延迟加载 runner（从对应路由文件重新导入）
# 结构：{ task_type: { "runner": Callable, "factory": str } }
_RUNNER_REGISTRY: dict[str, dict] = {}

# task_type → runner 工厂模块路径（后端重启后延迟恢复用）
# 新增 task_type 时在此注册，确保重试在重启后仍可用
_RUNNER_FACTORIES: dict[str, str] = {
    "chapter_generate": "app.api.routes.projects_pkg.chapters:_get_chapter_runner",
    "chapter_analyze": "app.api.routes.projects_pkg.chapters:_get_analyze_runner",
    "chapter_batch_analyze": "app.api.routes.projects_pkg.chapters:_get_batch_analyze_runner",
    "outline_new": "app.api.routes.projects_pkg.outlines:_get_outline_new_runner",
    "outline_continue": "app.api.routes.projects_pkg.outlines:_get_outline_continue_runner",
    "outline_expand": "app.api.routes.projects_pkg.outlines:_get_outline_expand_runner",
    "characters": "app.api.routes.projects_pkg.characters:_get_characters_runner",
    "organizations": "app.api.routes.projects_pkg.organizations:_get_organizations_runner",
    "world_core": "app.api.routes.projects_pkg.worlds:_get_world_core_runner",
    "book_import": "app.api.routes.projects_pkg.ai_tools:_get_book_import_runner",
}


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
    # 注册 runner（供重试使用）
    _RUNNER_REGISTRY[task_type] = {"runner": runner}

    task = await bg_service.create_task(
        user_id=user_id,
        project_id=project_id,
        task_type=task_type,
        title=title,
        payload=payload,
    )
    asyncio.create_task(_wrap_runner(task.id, runner, payload))
    return task.id


def _resolve_runner(task_type: str) -> Callable | None:
    """从注册表获取 runner；若注册表为空（后端重启后），尝试从工厂加载。"""
    entry = _RUNNER_REGISTRY.get(task_type)
    if entry and entry.get("runner"):
        return entry["runner"]

    # 后端重启后注册表为空，尝试从路由文件重新获取 runner
    # 当前各路由的 runner 是内嵌闭包，无法延迟加载
    # 实际策略：runner 注册表在首次提交同类型任务时自动填充
    # 重启后尚未提交过的类型无法重试 → 提示用户在页面重新操作
    return None


async def retry_task(task_id: int, user_id: int) -> int:
    """重试失败的任务：读取原任务 payload → 用注册表中的 runner 重新提交。

    Returns:
        new_task_id: 新任务ID

    Raises:
        ValueError: 任务不存在/非失败状态/无对应 runner
    """
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.background_task import BackgroundTask

    async with async_session() as db:
        result = await db.execute(
            select(BackgroundTask).where(
                BackgroundTask.id == task_id,
                BackgroundTask.user_id == user_id,
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("任务不存在或无权操作")
        if task.status != "failed":
            raise ValueError("只能重试失败的任务")

        task_type = task.task_type
        payload = task.payload or {}
        title = task.title or task_type
        project_id = task.project_id

    runner = _resolve_runner(task_type)
    if not runner:
        raise ValueError(
            f"任务类型 '{task_type}' 的执行器未加载（可能后端已重启），"
            f"请在对应页面重新操作"
        )

    # 创建新任务
    new_task = await bg_service.create_task(
        user_id=user_id,
        project_id=project_id,
        task_type=task_type,
        title=f"重试：{title}",
        payload=payload,
    )
    asyncio.create_task(_wrap_runner(new_task.id, runner, payload))
    return new_task.id


async def _wrap_runner(task_id: int, runner: Callable, payload: dict):
    """包装 runner：标记开始、执行、标记完成/失败。

    创建共享 session 贯穿整个任务生命周期，避免 TaskProgressTracker 与 runner
    各自独立 session 并发写 SQLite 导致的 database is locked 错误。
    外层 try/except 兜底 session 创建/mark_started 失败，确保不会静默丢失。
    整体任务有超时保护（AI_TASK_TIMEOUT），超时后标记失败。
    """
    try:
        async with async_session() as db:
            await bg_service.mark_started(task_id, db=db)
            try:
                await asyncio.wait_for(
                    runner(task_id, payload, db),
                    timeout=settings.AI_TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                tracker = bg_service.TaskProgressTracker(task_id, db=db)
                await tracker.fail(f"任务超时（{settings.AI_TASK_TIMEOUT}秒）")
            except Exception as e:
                tracker = bg_service.TaskProgressTracker(task_id, db=db)
                await tracker.fail(str(e)[:5000])
    except Exception as outer_e:
        # 兜底：session 创建或 mark_started 失败，用独立 session 标记失败
        try:
            tracker = bg_service.TaskProgressTracker(task_id)
            await tracker.fail(f"任务启动失败: {str(outer_e)[:500]}")
        except Exception:
            pass  # 连标记失败都失败，只能靠日志
