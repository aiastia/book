"""写作风格模型：可复用的风格预设 + 项目默认风格引用。

对标 MuMuAINovel 的 WritingStyle + ProjectDefaultStyle。
功能等价版：用户可创建多个风格预设，每个项目选一个作为默认。
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class WritingStyle(Base):
    """写作风格预设：节奏/语气/句式/描写侧重等，可被多个项目复用。"""

    __tablename__ = "writing_styles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # 风格名，如"快节奏爽文"/"细腻文艺"
    description = Column(Text, default="")
    # 作家名（可选）：仅用于展示与归类，如"鲁迅"
    author_name = Column(String(100), default="")

    # 结构化风格配置（章节生成时注入提示词）
    # 典型字段：pacing(节奏快/慢)、tone(语气)、sentence_length(句式长/短)、
    #           description_focus(描写侧重 动作/心理/环境)、dialogue_ratio(对话占比)、
    #           vocabulary(用词偏好)、pov(视角)
    config = Column(JSON, default=dict)
    # 用户自定义提示词（高级）：直接写给 AI 的写作风格指令，优先级高于维度配置
    custom_prompt = Column(Text, default="")

    # === 作家文风模仿（#25 增强）===
    # 范文原文：用户粘贴的目标作家原文片段（few-shot 原料）
    reference_text = Column(Text, default="")
    # AI 从范文中提炼出的结构化文风特征（仿写准则，生成时优先于范文使用）
    # 典型字段：sentence_pattern / vocabulary / imagery / rhythm / tone /
    #           signature_techniques / avoid_list / summary
    style_traits = Column(JSON, default=dict)
    # 特征最近一次提炼时间（用于判断范文是否已分析、是否需要重新分析）
    traits_updated_at = Column(DateTime, nullable=True)

    is_preset = Column(Boolean, default=False)  # 系统内置预设
    is_default = Column(Boolean, default=False)  # 用户默认风格（每用户仅一个）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author_name": self.author_name or "",
            "config": self.config,
            "custom_prompt": self.custom_prompt or "",
            "reference_text": self.reference_text or "",
            "style_traits": self.style_traits or {},
            "traits_updated_at": self.traits_updated_at.isoformat()
            if self.traits_updated_at
            else None,
            "is_preset": self.is_preset,
            "is_default": bool(self.is_default),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
