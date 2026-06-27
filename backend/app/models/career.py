"""职业体系模型：主/副职业 + 阶段进阶。

对标 MuMuAINovel 的 Career + CharacterCareer。功能等价轻量版：
- 一个项目有多条职业（主职业/副职业）
- 每条职业有进阶阶段（stages JSON）
- 角色通过 occupation 字段文本关联（保持简单，不强制外键）
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Career(Base):
    """职业/修炼体系：如「剑修」「炼丹师」「商人」及其阶段。"""

    __tablename__ = "careers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 职业名
    career_type = Column(String(20), default="main")  # main(主职业) / sub(副职业)
    category = Column(String(50), default="")  # 分类：战斗/辅助/生产/特殊
    description = Column(Text, default="")

    # 进阶阶段：[{name, level, requirement, ability, power_level}]
    stages = Column(JSON, default=list)

    # 特殊能力/属性加成
    abilities = Column(JSON, default=list)  # [{name, description, unlock_stage}]
    attributes = Column(JSON, default=dict)  # {attack: +10, defense: +5, ...}

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "career_type": self.career_type,
            "category": self.category,
            "description": self.description,
            "stages": self.stages,
            "abilities": self.abilities,
            "attributes": self.attributes,
        }
