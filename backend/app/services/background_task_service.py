"""通用后台任务服务。

对标 MuMuAINovel 的 BackgroundTaskService。
提供统一的任务创建/查询/取消/清理入口 + 进度状态机。

核心设计：
- fire-and-forget：提交接口建 pending 记录 → asyncio.create_task 执行
- 独立 session：执行协程用 async_session()，不复用请求 session
- 进度状态机：pending → running(stage 机) → completed/failed/cancelled
- 取消：置 cancel_requested=True，执行协程检查后优雅退出

使用示例（在路由层）：
    task = await bg_service.create_task(user_id, project_id, "chapter_batch",
                                        title="批量生成章节", payload={...})
    asyncio.create_task(run_batch(task.id))
    return {"task_id": task.id}

执行协程内：
    tracker = TaskProgressTracker(task_id)
    await tracker.update(stage="generating", progress=30, message="生成第3章...")
    if await tracker.is_cancelled():
        return
"""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.background_task import BackgroundTask

# 进度阶段机（参照 MuMu TaskProgressTracker）
STAGE_PROGRESS = {
    "init": 0,
    "loading": 5,  # 加载上下文
    "preparing": 17,  # 组装提示词
    "generating": 20,  # 调用 AI
    "parsing": 88,  # 解析结果
    "saving": 92,  # 落库
    "complete": 100,
}


class TaskProgressTracker:
    """进度追踪器：在执行协程内更新任务状态。

    每次更新写库，确保前端轮询能拿到最新进度。
    传入 db 参数时复用已有 session（避免 SQLite 写锁冲突），否则自行创建。
    """

    def __init__(self, task_id: int, db: AsyncSession | None = None):
        self.task_id = task_id
        self._db = db

    async def _get_db(self):
        if self._db is not None:
            return self._db
        return async_session()

    async def update(
        self,
        stage: str | None = None,
        progress: int | None = None,
        message: str = "",
        progress_details: dict | None = None,
    ):
        """更新任务进度。progress 可省略（按 stage 自动算）。"""
        if progress is None and stage:
            progress = STAGE_PROGRESS.get(stage, 50)
        task_data = None
        async with await self._get_db() as db:
            values = {
                "status": "running",
                "updated_at": datetime.utcnow(),
            }
            if stage:
                values["stage"] = stage
            if progress is not None:
                values["progress"] = min(99, max(0, progress))  # 完成前不超过99
            if message:
                values["status_message"] = message[:500]
            if progress_details is not None:
                values["progress_details"] = progress_details
            await db.execute(
                update(BackgroundTask).where(BackgroundTask.id == self.task_id).values(**values)
            )
            await db.commit()
            # 获取完整任务数据用于 WebSocket 推送
            task = (
                await db.execute(select(BackgroundTask).where(BackgroundTask.id == self.task_id))
            ).scalar_one_or_none()
            if task:
                task_data = task.to_dict()

        # WebSocket 推送
        if task_data:
            await self._ws_broadcast(task_data)

    async def complete(self, result: dict = None, message: str = "完成"):
        """标记任务完成。"""
        task_data = None
        async with await self._get_db() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.id == self.task_id)
                .values(
                    status="completed",
                    progress=100,
                    stage="complete",
                    status_message=message[:500],
                    result=result or {},
                    completed_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            await db.commit()
            task = (
                await db.execute(select(BackgroundTask).where(BackgroundTask.id == self.task_id))
            ).scalar_one_or_none()
            if task:
                task_data = task.to_dict()

        if task_data:
            await self._ws_broadcast(task_data)

    async def fail(self, error: str):
        """标记任务失败。"""
        task_data = None
        async with await self._get_db() as db:
            await db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.id == self.task_id)
                .values(
                    status="failed",
                    error=error[:5000],
                    completed_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            await db.commit()
            task = (
                await db.execute(select(BackgroundTask).where(BackgroundTask.id == self.task_id))
            ).scalar_one_or_none()
            if task:
                task_data = task.to_dict()

        if task_data:
            await self._ws_broadcast(task_data)

    async def _ws_broadcast(self, task_data: dict):
        """通过 WebSocket 推送任务状态更新。"""
        try:
            from app.api.routes.ws_tasks import broadcast_task_update

            uid = task_data.get("user_id")
            if uid:
                await broadcast_task_update(uid, task_data)
        except Exception:
            pass  # WebSocket 推送失败不影响主流程

    async def is_cancelled(self) -> bool:
        """检查任务是否被取消（执行协程内调用，优雅退出）。"""
        async with await self._get_db() as db:
            row = (
                await db.execute(
                    select(BackgroundTask.cancel_requested, BackgroundTask.status).where(
                        BackgroundTask.id == self.task_id
                    )
                )
            ).first()
            if not row:
                return True
            return bool(row[0]) or row[1] == "cancelled"


async def create_task(
    user_id: int,
    project_id: int | None,
    task_type: str,
    title: str = "",
    payload: dict | None = None,
    db: AsyncSession | None = None,
) -> BackgroundTask:
    """创建一个 pending 任务记录（在请求 session 内调用）。"""

    async def _create(session: AsyncSession) -> BackgroundTask:
        task = BackgroundTask(
            user_id=user_id,
            project_id=project_id,
            task_type=task_type,
            title=title or task_type,
            status="pending",
            payload=payload or {},
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task

    if db is not None:
        return await _create(db)
    async with async_session() as session:
        return await _create(session)


async def get_task(task_id: int) -> dict | None:
    """查询单个任务（轮询用）。"""
    async with async_session() as db:
        task = (
            await db.execute(select(BackgroundTask).where(BackgroundTask.id == task_id))
        ).scalar_one_or_none()
        return task.to_dict() if task else None


async def list_user_tasks(
    user_id: int,
    project_id: int | None = None,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """列出用户任务（活跃任务优先）。"""
    async with async_session() as db:
        stmt = select(BackgroundTask).where(BackgroundTask.user_id == user_id)
        if project_id:
            stmt = stmt.where(BackgroundTask.project_id == project_id)
        if status:
            stmt = stmt.where(BackgroundTask.status == status)
        if task_type:
            stmt = stmt.where(BackgroundTask.task_type == task_type)
        # 活跃（pending/running）优先，再按创建时间倒序
        stmt = stmt.order_by(
            BackgroundTask.status.in_(["pending", "running"]).desc(),
            BackgroundTask.created_at.desc(),
        ).limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [t.to_dict() for t in rows]


async def list_active_tasks(user_id: int, project_id: int | None = None) -> list[dict]:
    """列出活跃任务（pending/running）。"""
    async with async_session() as db:
        stmt = select(BackgroundTask).where(
            BackgroundTask.user_id == user_id,
            BackgroundTask.status.in_(["pending", "running"]),
        )
        if project_id:
            stmt = stmt.where(BackgroundTask.project_id == project_id)
        stmt = stmt.order_by(BackgroundTask.created_at.desc())
        rows = (await db.execute(stmt)).scalars().all()
        return [t.to_dict() for t in rows]


async def cancel_task(task_id: int, user_id: int) -> bool:
    """请求取消任务（置 cancel_requested=True）。

    执行协程检查 is_cancelled() 后优雅退出。
    若任务已是终态，直接置 cancelled。
    """
    async with async_session() as db:
        task = (
            await db.execute(
                select(BackgroundTask).where(
                    BackgroundTask.id == task_id,
                    BackgroundTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not task:
            return False
        if task.status in ("pending", "running"):
            task.cancel_requested = True
            # pending 任务可直接置 cancelled；running 等执行协程自行退出
            if task.status == "pending":
                task.status = "cancelled"
                task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            await db.commit()
        return True


async def delete_task(task_id: int, user_id: int) -> bool:
    """删除任务记录（仅终态可删）。"""
    async with async_session() as db:
        task = (
            await db.execute(
                select(BackgroundTask).where(
                    BackgroundTask.id == task_id,
                    BackgroundTask.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not task:
            return False
        if task.status not in ("completed", "failed", "cancelled"):
            return False
        await db.delete(task)
        await db.commit()
        return True


async def cleanup_old_tasks(days: int = 7) -> int:
    """清理 N 天前的已完成/失败/取消任务。返回删除条数。"""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session() as db:
        result = await db.execute(
            delete(BackgroundTask).where(
                BackgroundTask.status.in_(["completed", "failed", "cancelled"]),
                BackgroundTask.created_at < cutoff,
            )
        )
        await db.commit()
        return result.rowcount


async def mark_started(task_id: int, db: AsyncSession | None = None):
    """任务开始执行时调用（pending → running）。"""
    if db is not None:
        await db.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task_id)
            .values(
                status="running",
                stage="init",
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()
        return
    async with async_session() as db:
        await db.execute(
            update(BackgroundTask)
            .where(BackgroundTask.id == task_id)
            .values(
                status="running",
                stage="init",
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()
