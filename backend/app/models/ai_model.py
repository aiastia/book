"""AI 模型配置"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Boolean
from app.core.database import Base


class AIModelConfig(Base):
    """用户级 AI 模型配置"""
    __tablename__ = "ai_model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), default="默认")  # 配置名称
    base_url = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=False)
    model = Column(String(100), nullable=False)
    temperature = Column(Integer, default=85)  # *100 存储
    top_p = Column(Integer, default=90)
    max_tokens = Column(Integer, default=4096)
    frequency_penalty = Column(Integer, nullable=True, default=None)  # *100 存储，NULL=不发送
    presence_penalty = Column(Integer, nullable=True, default=None)   # *100 存储，NULL=不发送
    is_default = Column(Boolean, default=False)
    # 推理模型标记（Kimi K2 / DeepSeek-R1 / o1-o3 等）：勾选后强制 temperature=1，不发送 top_p/penalty
    reasoning_model = Column(Boolean, default=False)
    backend_type = Column(String(20), default="openai")  # openai, claude_code（兼容字段）
    # AI 厂商：openai(openai兼容，含 deepseek/moonshot/自定义)、anthropic、gemini
    provider = Column(String(20), default="openai")
    # embedding 模型（用于记忆向量检索，可选）
    embedding_model = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)