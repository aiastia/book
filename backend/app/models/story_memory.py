"""故事记忆模型"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base


class StoryMemory(Base):
    __tablename__ = "story_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=True)
    chapter_number = Column(Integer, nullable=True)
    memory_type = Column(
        String(50), default=""
    )  # plot/character/world/relationship/hook/foreshadow/scene
    title = Column(String(200), default="")
    content = Column(Text, nullable=False)  # 记忆内容
    importance = Column(Float, default=0.5)  # 重要度 0-1
    # 向量检索相关
    embedding = Column(JSON, nullable=True)  # 向量嵌入（冗余缓存，向量检索的主存储在 ChromaDB）
    vector_id = Column(String(100), default="", index=True)  # ChromaDB 中的 id
    embedding_model = Column(String(100), default="")
    tags = Column(JSON, default=list)
    related_characters = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
