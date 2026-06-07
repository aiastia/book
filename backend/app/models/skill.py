"""Skill 插件模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, Boolean
from app.core.database import Base


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(100), default="")
    description = Column(Text, default="")
    category = Column(String(50), default="")  # outline, chapter, analysis, character, foreshadow
    skill_type = Column(String(20), default="builtin")  # builtin, custom, mcp
    # Skill 执行配置
    system_prompt = Column(Text, default="")
    pre_hooks = Column(JSON, default=list)  # 执行前钩子 [{type, config}]
    post_hooks = Column(JSON, default=list)  # 执行后钩子
    parameters = Column(JSON, default=dict)  # 参数 schema
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # 扩展配置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SkillConfig(Base):
    """用户级 Skill 配置（覆盖系统默认）"""
    __tablename__ = "skill_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    skill_id = Column(Integer, ForeignKey("skills.id"), nullable=False)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # 用户自定义配置覆盖
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)