"""应用配置"""

import os

from pydantic_settings import BaseSettings


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
    AI_MAX_TOKENS: int = 200000  # 单次请求最大输出 token 数（全局上限，覆盖 skill 配置）
    AI_DEFAULT_MAX_TOKENS: int = 26384  # 默认输出 token 数（skill 未配置时使用）
    # frequency_penalty / presence_penalty 不在全局强制默认值。
    # 由用户 AI 设置页逐个模型配置，None 时不发送参数以兼容不支持这些参数的模型。

    # AI 超时和重试配置（环境变量：MOYU_AI_TIMEOUT / MOYU_AI_MAX_RETRIES）
    AI_TIMEOUT: int = 600  # 读写超时（秒），默认 10 分钟（复杂提示词需要更长推理时间）
    AI_CONNECT_TIMEOUT: int = 120  # 连接超时（秒）
    AI_SDK_MAX_RETRIES: int = (
        0  # OpenAI SDK 层 HTTP 重试次数（0=不重试，避免 SDK 透明重试导致重复计费）
    )
    AI_MAX_RETRIES: int = 1  # 应用层 JSON 解析重试次数（仅重试 1 次，减少 token 浪费）
    AI_RETRY_DELAY: float = 3.0  # 重试基础间隔（秒），指数退避
    AI_RETRY_MAX_DELAY: float = 30.0  # 重试最大间隔（秒）

    # 章节生成参数
    CHAPTER_DEFAULT_WORDS: int = 4000
    CHAPTER_MIN_WORDS: int = 3000
    CHAPTER_MAX_WORDS: int = 6000
    CHAPTER_CONTEXT_CHAPTERS: int = 10  # 上下文章节数
    CHAPTER_CONTEXT_WORDS: int = 500  # 衔接锚点字数
    VOLUME_SIZE: int = 10  # 每卷章节数（每 N 章生成一个卷摘要）
    OUTLINE_CONTEXT_CHAPTERS: int = 20  # 大纲续写时带入的最近章节数（超出部分精简）
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
