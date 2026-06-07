"""批量章节生成任务模型（#12）。

对标 MuMuAINovel BatchGenerationTask。
承载批量顺序生成多个章节的后台任务，逐章生成 + 跨章上下文传递 + 取消。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from app.core.database import Base


class BatchGenerationTask(Base):
    __tablename__ = "batch_generation_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    # 待生成的章节 ID 列表
    chapter_ids = Column(JSON, default=list)
    # 统计
    total_chapters = Column(Integer, default=0)
    completed_chapters = Column(Integer, default=0)
    failed_chapters = Column(JSON, default=list)  # [{chapter_id, chapter_number, error}]
    # 当前进度
    current_chapter_id = Column(Integer, nullable=True)
    current_chapter_number = Column(Integer, nullable=True)
    current_index = Column(Integer, default=0)  # 当前在第几个（0-based）
    # 重试
    current_retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=2)
    # 配置
    enable_analysis = Column(Boolean, default=True)  # 生成后是否自动分析
    target_word_count = Column(Integer, default=3000)
    # 状态：pending/running/completed/failed/cancelled
    status = Column(String(20), default="pending", index=True)
    progress = Column(Integer, default=0)  # 0-100
    status_message = Column(String(500), default="")
    error = Column(String(2000), default="")
    cancel_requested = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "chapter_ids": self.chapter_ids or [],
            "total_chapters": self.total_chapters,
            "completed_chapters": self.completed_chapters,
            "failed_chapters": self.failed_chapters or [],
            "current_chapter_id": self.current_chapter_id,
            "current_chapter_number": self.current_chapter_number,
            "current_index": self.current_index,
            "current_retry_count": self.current_retry_count,
            "max_retries": self.max_retries,
            "enable_analysis": self.enable_analysis,
            "target_word_count": self.target_word_count,
            "status": self.status,
            "progress": self.progress,
            "status_message": self.status_message,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
