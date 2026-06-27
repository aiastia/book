"""关系变化日志模型。

记录角色关系在每个章节后的变化（亲密度升降、关系类型转变等），
同时保存完整快照供回溯到任意章节。
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class RelationChangeLog(Base):
    __tablename__ = "relation_change_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    relation_id = Column(
        Integer,
        ForeignKey("character_relations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 发生在第几章
    chapter_number = Column(Integer, nullable=False)
    # 变更了哪些字段：{"intimacy": {"old": 20, "new": 45}, "relation_type": "宿敌→同盟"}
    changed_fields = Column(JSON, default=dict)
    # 该章节之后的关系完整状态快照
    snapshot = Column(JSON, default=dict)
    # 人类可读摘要
    summary = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "relation_id": self.relation_id,
            "chapter_number": self.chapter_number,
            "changed_fields": self.changed_fields or {},
            "snapshot": self.snapshot or {},
            "summary": self.summary or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
