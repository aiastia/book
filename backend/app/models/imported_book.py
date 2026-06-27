"""拆书导入书籍模型。

承载上传的小说原文（TXT），用于后续 AI 反向拆解（提炼立项信息 + 生成章节大纲）。
全量正文存 raw_text，采样时按需切分（见 ai_tools 路由）。
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


class ImportedBook(Base):
    """导入的待拆解书籍。"""

    __tablename__ = "imported_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), default="")  # 书名（来自文件名或用户输入）
    source_filename = Column(String(300), default="")  # 原始文件名
    total_chapters = Column(Integer, default=0)  # 解析出的总章数
    total_chars = Column(Integer, default=0)  # 总字数
    raw_text = Column(Text, default="")  # 完整正文（采样取章节用）
    has_strong_titles = Column(Integer, default=0)  # 章节标记是否清晰 0/1
    # imported(已导入) / project_created(已拆解生成项目)
    status = Column(String(20), default="imported", index=True)
    # 拆解后生成的项目 id
    created_project_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """列表用序列化，不含 raw_text（可能很大）。"""
        return {
            "id": self.id,
            "title": self.title or "",
            "source_filename": self.source_filename or "",
            "total_chapters": self.total_chapters or 0,
            "total_chars": self.total_chars or 0,
            "has_strong_titles": self.has_strong_titles or 0,
            "status": self.status or "imported",
            "created_project_id": self.created_project_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
