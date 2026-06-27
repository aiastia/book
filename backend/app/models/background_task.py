"""通用后台任务模型。

对标 MuMuAINovel 的 BackgroundTask。统一承载所有长耗时异步任务：
- 大纲生成/续写/展开
- 章节生成/批量生成
- 世界观/物品/地点批量生成
- 拆书导入

设计：fire-and-forget + 独立 session + 逐步更新 progress。
前端通过 /api/tasks 轮询进度，可取消。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class BackgroundTask(Base):
    """通用后台任务记录。"""

    __tablename__ = "background_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    # 任务类型：outline_new/outline_continue/outline_expand/chapter_generate/chapter_batch/
    # wizard/world/organizations/characters/items/locations/book_import 等
    task_type = Column(String(50), nullable=False, index=True)
    # 任务标题（前端展示用）
    title = Column(String(200), default="")
    # 状态：pending/running/completed/failed/cancelled
    status = Column(String(20), default="pending", index=True)
    progress = Column(Integer, default=0)  # 0-100
    status_message = Column(String(500), default="")
    # 阶段信息（loading/preparing/generating/parsing/saving/complete）
    stage = Column(String(30), default="")
    # 详细进度（如 {current:3, total:10, failed:[chapter_id,...]}）
    progress_details = Column(JSON, default=dict)
    # 任务参数（创建时的请求体快照，便于重试）
    payload = Column(JSON, default=dict)
    # 任务结果（完成后填充）
    result = Column(JSON, default=dict)
    error = Column(Text, default="")
    # 取消请求标志
    cancel_requested = Column(Boolean, default=False)
    # 重试相关
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "task_type": self.task_type,
            "title": self.title or self.task_type,
            "status": self.status,
            "progress": self.progress,
            "status_message": self.status_message,
            "stage": self.stage,
            "progress_details": self.progress_details or {},
            "result": self.result or {},
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
