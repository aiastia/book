"""世界观模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from app.core.database import Base


class WorldSetting(Base):
    __tablename__ = "world_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), default="")  # 地理/历史/魔法体系/科技体系/社会制度
    content = Column(Text, default="")  # 详细描述
    structure = Column(JSON, default=dict)  # JSON 扩展数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)