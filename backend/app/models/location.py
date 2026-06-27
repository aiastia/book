"""地点/地图系统模型。

对标 MuMuAINovel（无独立模型，本系统为自创增强）。
承载城市/区域/建筑/秘境等地理实体，支持层级关系（父子地点）。
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Location(Base):
    """地点。支持自引用层级（parent_location_id）。"""

    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # 类型：城市/区域/建筑/秘境/自然景观/国家/大陆/其他
    location_type = Column(String(50), default="城市", index=True)
    # 层级：父地点（自引用，null=顶级地点）
    parent_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    level = Column(Integer, default=0)  # 层级深度，0=顶级
    description = Column(Text, default="")
    # 氛围/特色（如「繁华喧嚣」「阴森诡异」「灵气充沛」）
    atmosphere = Column(Text, default="")
    # 控制势力（组织名或描述）
    faction_control = Column(String(200), default="")
    faction_org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    # 地理特征（地形/气候/资源）
    geography = Column(Text, default="")
    # 重要性：minor(次要)/normal(普通)/major(重要)/key(关键)
    importance = Column(String(20), default="normal")
    # 首次出现章节
    first_appear_chapter = Column(Integer, nullable=True)
    # 关联角色（常驻此地的人物）
    resident_character_ids = Column(JSON, default=list)
    # 隐藏/危险等级（秘境用）：safe/dangerous/forbidden/unknown
    danger_level = Column(String(20), default="safe")
    # 排序
    sort_order = Column(Integer, default=0)
    # 来源
    source = Column(String(20), default="manual")  # ai/manual/analysis
    structure = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "location_type": self.location_type,
            "parent_location_id": self.parent_location_id,
            "level": self.level,
            "description": self.description,
            "atmosphere": self.atmosphere,
            "faction_control": self.faction_control,
            "faction_org_id": self.faction_org_id,
            "geography": self.geography,
            "importance": self.importance,
            "first_appear_chapter": self.first_appear_chapter,
            "resident_character_ids": self.resident_character_ids or [],
            "danger_level": self.danger_level,
            "sort_order": self.sort_order,
            "source": self.source,
            "structure": self.structure or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
