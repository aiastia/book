"""生成历史模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class GenerationHistory(Base):
    __tablename__ = "generation_histories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)
    prompt_name = Column(String(100), default="")  # 使用的提示词模板名称
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=True)
    model_used = Column(String(100), default="")
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    duration_ms = Column(Integer, default=0)
    status = Column(String(20), default="success")  # success, failed, partial
    error_message = Column(Text, default="")
    request_payload = Column(JSON, default=dict)
    response_preview = Column(Text, default="")  # 响应前500字
    created_at = Column(DateTime, default=datetime.utcnow)
