"""章节重写任务模型（#11）。

对标 MuMuAINovel RegenerationTask。承载章节重写的版本快照，
保留原文/重写文/修改指令/版本号，支持版本对比与回溯。
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class RegenerationTask(Base):
    __tablename__ = "regeneration_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(
        Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 修改指令（综合：分析建议 + 用户自定义 + 聚焦领域）
    modification_instructions = Column(Text, default="")
    focus_areas = Column(JSON, default=list)  # [pacing/emotion/description/dialogue/conflict]
    preserve_elements = Column(JSON, default=list)  # 要保留的元素
    length_mode = Column(String(20), default="similar")  # similar/expand/condense/custom
    target_word_count = Column(Integer, nullable=True)
    # 原文快照
    original_content = Column(Text, default="")
    original_word_count = Column(Integer, default=0)
    # 重写结果
    regenerated_content = Column(Text, default="")
    regenerated_word_count = Column(Integer, default=0)
    # 版本
    version_number = Column(Integer, default=1)
    version_note = Column(String(500), default="")
    is_applied = Column(Integer, default=0)  # 0/1 是否已应用（覆盖章节）
    # 状态：pending/running/completed/failed
    status = Column(String(20), default="pending", index=True)
    error = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "chapter_id": self.chapter_id,
            "modification_instructions": self.modification_instructions or "",
            "focus_areas": self.focus_areas or [],
            "preserve_elements": self.preserve_elements or [],
            "length_mode": self.length_mode or "similar",
            "target_word_count": self.target_word_count,
            "original_word_count": self.original_word_count or 0,
            "regenerated_word_count": self.regenerated_word_count or 0,
            "regenerated_content": self.regenerated_content or "",
            "version_number": self.version_number or 1,
            "version_note": self.version_note or "",
            "is_applied": self.is_applied or 0,
            "status": self.status,
            "error": self.error or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
