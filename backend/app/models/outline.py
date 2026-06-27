"""大纲模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Outline(Base):
    __tablename__ = "outlines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    outline_type = Column(String(20), default="chapter")  # chapter, arc, full
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(200), default="")
    summary = Column(Text, default="")  # 章节摘要
    scenes = Column(JSON, default=list)  # [{scene_title, scene_desc, emotion}]
    characters = Column(JSON, default=list)  # 涉及角色 id 列表
    key_points = Column(JSON, default=list)  # 关键情节点
    emotion = Column(String(50), default="")  # 本章主情绪
    goal = Column(Text, default="")  # 本章写作目标
    structure = Column(JSON, default=dict)  # JSON 扩展数据（包含 AI 生成的完整大纲字段）
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
