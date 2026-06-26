"""MCP 服务器配置模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from app.core.database import Base


class McpServer(Base):
    """MCP 服务器配置"""
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)  # MCP server URL (http:// or ws://)
    transport = Column(String(20), default="stdio")  # stdio / sse / streamable-http
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)  # 额外配置（headers, auth, env等）
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "url": self.url,
            "transport": self.transport, "enabled": self.enabled,
            "config": self.config, "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
