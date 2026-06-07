"""角色职业关联模型。

对标 MuMuAINovel CharacterCareer。承载角色修炼/从事的职业及其当前阶段进度。
与剧情分析联动：分析输出 character_states[].career_changes 时自动更新阶段。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, UniqueConstraint
from app.core.database import Base


class CharacterCareer(Base):
    """角色职业关联（角色修炼某职业的进度记录）。"""
    __tablename__ = "character_careers"
    __table_args__ = (
        UniqueConstraint("character_id", "career_id", name="uq_char_career"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    career_id = Column(Integer, ForeignKey("careers.id", ondelete="CASCADE"), nullable=False, index=True)
    # 职业类型：main(主职业)/sub(副职业)
    career_type = Column(String(20), default="main")
    # 当前阶段（数字）
    current_stage = Column(Integer, default=1)
    # 阶段进度 0-100（百分比）
    stage_progress = Column(Integer, default=0)
    # 开始时间/到达当前阶段时间（故事时间描述）
    started_at = Column(String(100), default="")
    reached_current_stage_at = Column(String(100), default="")
    notes = Column(Text, default="")
    # 来源
    source = Column(String(20), default="manual")  # ai/manual/analysis
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "character_id": self.character_id,
            "career_id": self.career_id,
            "career_type": self.career_type,
            "current_stage": self.current_stage,
            "stage_progress": self.stage_progress,
            "started_at": self.started_at,
            "reached_current_stage_at": self.reached_current_stage_at,
            "notes": self.notes,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
