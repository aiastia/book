"""章节模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    outline_id = Column(Integer, ForeignKey("outlines.id"), nullable=True)
    chapter_number = Column(Integer, nullable=False)
    sub_index = Column(Integer, default=1)  # 1对多模式下，大纲内的子章节序号（从1开始）
    title = Column(String(200), default="")
    content = Column(Text, default="")
    summary = Column(Text, default="")  # 章节摘要
    word_count = Column(Integer, default=0)
    status = Column(String(20), default="draft")  # draft, generating, completed, reviewed
    generation_mode = Column(String(20), default="one_to_one")  # one_to_one, one_to_many
    expansion_plan = Column(JSON, default=dict)  # 1-N 模式的扩展计划
    quality_score = Column(Float, nullable=True)  # 综合质量评分
    quality_detail = Column(JSON, default=dict)  # 评分明细
    quality_alert = Column(
        String(50), default=""
    )  # 质量告警：low_score/consistency_issue/low_coherence
    raw_output = Column(Text, default="")  # 清理/改写前的原始 AI 输出
    generation_history = Column(JSON, default=list)  # 生成历史记录
    style_config = Column(JSON, default=dict)  # 本章写作风格覆盖
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
