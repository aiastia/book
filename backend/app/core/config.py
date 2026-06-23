"""应用配置"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "墨语 AI 小说创作平台"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "moyu-secret-change-in-production-2024"

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/moyu.db"

    # AI 模型配置 - 自定义 OpenAI 兼容
    AI_BASE_URL: str = "https://api.openai.com/v1"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o"
    AI_TEMPERATURE: float = 0.85
    AI_TOP_P: float = 0.9
    AI_MAX_TOKENS: int = 4096

    # 章节生成参数
    CHAPTER_DEFAULT_WORDS: int = 2500
    CHAPTER_MIN_WORDS: int = 2000
    CHAPTER_MAX_WORDS: int = 3500
    CHAPTER_CONTEXT_CHAPTERS: int = 10  # 上下文章节数
    CHAPTER_CONTEXT_WORDS: int = 500   # 衔接锚点字数
    VOLUME_SIZE: int = 10              # 每卷章节数（每 N 章生成一个卷摘要）
    OUTLINE_CONTEXT_CHAPTERS: int = 20 # 大纲续写时带入的最近章节数（超出部分精简）
    MEMORY_SIMILARITY_THRESHOLD: float = 0.6
    QUALITY_TREND_COUNT: int = 5  # 评分趋势章节数
    FORESHADOW_LOOKAHEAD: int = 3  # 伏笔前瞻章节数

    # 服务器
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # 数据目录
    DATA_DIR: str = "./data"

    class Config:
        env_file = ".env"
        env_prefix = "MOYU_"


settings = Settings()

# 确保数据目录存在
os.makedirs(settings.DATA_DIR, exist_ok=True)