"""小说项目模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    genre = Column(String(50), default="")  # 体裁：玄幻/都市/科幻/言情
    synopsis = Column(Text, default="")  # 简介
    cover_url = Column(String(500), default="")
    target_word_count = Column(Integer, default=0)  # 目标总字数
    current_word_count = Column(Integer, default=0)  # 当前总字数
    chapter_count = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, paused, completed, archived
    writing_style = Column(JSON, default=dict)  # 写作风格配置
    narrative_pov = Column(String(50), default="第三人称")  # 叙事视角
    settings = Column(JSON, default=dict)  # 项目级设置
    # ---- 核心世界观（对标 MuMuAINovel） ----
    world_time_period = Column(Text, default="")  # 时间背景
    world_location = Column(Text, default="")  # 地理位置与世界
    world_atmosphere = Column(Text, default="")  # 氛围基调
    world_rules = Column(Text, default="")  # 世界规则（力量体系/社会法则）
    cover_prompt = Column(Text, default="")  # 封面提示词
    pen_name = Column(String(100), default="")  # 笔名/作者名（用于封面和导出）
    # ---- 大纲章节模式（对标 MuMuAINovel，创建后不可更改）----
    # one_to_one: 传统模式，1大纲→1章节（生成大纲时自动建章）
    # one_to_many: 细化模式，1大纲→N章节（大纲是"卷"，需手动展开为多章）
    outline_mode = Column(String(20), default="one_to_one", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
