"""伏笔模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Foreshadow(Base):
    __tablename__ = "foreshadows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")  # 伏笔内容描述
    foreshadow_type = Column(String(50), default="")  # 悬念/情感/认知/线索
    status = Column(String(20), default="pending")  # pending, planted, resolved, abandoned
    source_type = Column(String(20), default="manual")  # manual, planned, analysis
    plant_chapter_number = Column(Integer, nullable=True)  # 计划埋入章节
    actual_plant_chapter = Column(Integer, nullable=True)  # 实际埋入章节
    target_resolve_chapter_number = Column(Integer, nullable=True)  # 计划回收章节
    actual_resolve_chapter = Column(Integer, nullable=True)  # 实际回收章节
    priority = Column(Integer, default=5)  # 优先级 1-10
    tags = Column(JSON, default=list)
    structure = Column(JSON, default=dict)  # JSON 扩展数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
