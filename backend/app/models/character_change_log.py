"""角色变化日志模型。

记录角色在每个章节后的属性/状态变化，同时保存完整快照供章节生成时回溯。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from app.core.database import Base


class CharacterChangeLog(Base):
    __tablename__ = "character_change_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    # 发生在第几章
    chapter_number = Column(Integer, nullable=False)
    # 变更了哪些字段：{"status": "injured", "personality": "变得阴郁"}
    changed_fields = Column(JSON, default=dict)
    # 该章节之后的角色完整状态快照（供回溯到任意章节时使用）
    snapshot = Column(JSON, default=dict)
    # 人类可读摘要
    summary = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "character_id": self.character_id,
            "chapter_number": self.chapter_number,
            "changed_fields": self.changed_fields or {},
            "snapshot": self.snapshot or {},
            "summary": self.summary or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
