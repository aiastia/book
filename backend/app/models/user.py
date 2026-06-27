"""用户模型"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=True)
    password_hash = Column(String(128), nullable=False)
    nickname = Column(String(50), default="")
    avatar_url = Column(String(500), default="")
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # #4 管理员标志
    oauth_provider = Column(String(20), nullable=True)  # github, linuxdo
    oauth_id = Column(String(100), nullable=True)
    settings = Column(JSON, default=dict)  # 用户级设置
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
