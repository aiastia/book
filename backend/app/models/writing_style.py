"""写作风格模型：可复用的风格预设 + 项目默认风格引用。

对标 MuMuAINovel 的 WritingStyle + ProjectDefaultStyle。
功能等价版：用户可创建多个风格预设，每个项目选一个作为默认。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON
from app.core.database import Base


class WritingStyle(Base):
    """写作风格预设：节奏/语气/句式/描写侧重等，可被多个项目复用。"""
    __tablename__ = "writing_styles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 风格名，如"快节奏爽文"/"细腻文艺"
    description = Column(Text, default="")

    # 结构化风格配置（章节生成时注入提示词）
    # 典型字段：pacing(节奏快/慢)、tone(语气)、sentence_length(句式长/短)、
    #           description_focus(描写侧重 动作/心理/环境)、dialogue_ratio(对话占比)、
    #           vocabulary(用词偏好)、pov(视角)
    config = Column(JSON, default=dict)
    # 用户自定义提示词（高级）：直接写给 AI 的写作风格指令，优先级高于维度配置
    custom_prompt = Column(Text, default="")

    is_preset = Column(Boolean, default=False)  # 系统内置预设
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "config": self.config, "custom_prompt": self.custom_prompt or "",
            "is_preset": self.is_preset,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
