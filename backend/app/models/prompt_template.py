"""提示词模板模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, Boolean
from app.core.database import Base


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null=系统级
    name = Column(String(100), nullable=False)  # OUTLINE_CREATE, CHAPTER_GENERATION 等
    category = Column(String(50), default="")  # outline, chapter, analysis, character
    description = Column(Text, default="")
    is_system = Column(Boolean, default=True)  # 是否系统内置
    current_version_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(Integer, ForeignKey("prompt_templates.id"), nullable=False, index=True)
    version = Column(Integer, default=1)
    system_prompt = Column(Text, default="")
    user_prompt = Column(Text, default="")
    variables = Column(JSON, default=list)  # [{name, description, type, default}]
    config = Column(JSON, default=dict)  # {model, temperature, top_p, max_tokens, skill_ids}
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)