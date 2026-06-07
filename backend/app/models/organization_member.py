"""组织成员模型。

对标 MuMuAINovel OrganizationMember。承载角色在组织中的职位/等级/忠诚度/贡献度。
组织本身的层级字段（parent_org_id/level/power_level）加在 Organization 模型上。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, UniqueConstraint
from app.core.database import Base


class OrganizationMember(Base):
    """组织成员（角色在某组织的任职记录）。"""
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "character_id", name="uq_org_member"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    # 职位（宗主/长老/弟子/护法...）
    position = Column(String(100), default="")
    # 等级（数字，越大越高）
    rank = Column(Integer, default=0)
    # 状态：active(在职)/retired(退隐)/expelled(驱逐)/deceased(已故)
    status = Column(String(20), default="active")
    # 忠诚度 0-100
    loyalty = Column(Integer, default=50)
    # 贡献度 0-100
    contribution = Column(Integer, default=0)
    # 加入/离开（故事时间，章节号或描述）
    joined_at = Column(String(100), default="")
    left_at = Column(String(100), default="")
    notes = Column(Text, default="")
    # 来源
    source = Column(String(20), default="manual")  # ai/manual
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "organization_id": self.organization_id,
            "character_id": self.character_id,
            "position": self.position,
            "rank": self.rank,
            "status": self.status,
            "loyalty": self.loyalty,
            "contribution": self.contribution,
            "joined_at": self.joined_at,
            "left_at": self.left_at,
            "notes": self.notes,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
