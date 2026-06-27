"""项目初始化后台任务：异步生成世界观/角色/大纲，让用户提交后可自由切页。

对标 MuMuAINovel 的 BackgroundTask。功能等价轻量版：
- 提交后立即返回任务ID，后端 asyncio.create_task 异步执行
- 前端轮询 /status 查进度，不阻塞页面
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class ProjectInitTask(Base):
    """项目初始化任务：记录异步生成进度。"""

    __tablename__ = "project_init_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_type = Column(
        String(50), default="init"
    )  # init(完整初始化) / world / characters / outline
    status = Column(String(20), default="pending")  # pending/running/completed/failed
    progress = Column(Integer, default=0)  # 0-100
    status_message = Column(String(500), default="")
    # 各步骤完成情况（8 步完整流程）
    world_done = Column(Integer, default=0)
    career_done = Column(Integer, default=0)
    org_done = Column(Integer, default=0)
    characters_done = Column(Integer, default=0)
    assign_careers_done = Column(Integer, default=0)
    relations_done = Column(Integer, default=0)
    assign_org_members_done = Column(Integer, default=0)
    locations_done = Column(Integer, default=0)
    items_done = Column(Integer, default=0)
    outline_done = Column(Integer, default=0)
    validate_done = Column(Integer, default=0)
    # 失败信息
    failed_step = Column(String(100), default="")  # 失败的步骤名（用于 resume）
    error = Column(String(1000), default="")
    # 取消标志
    cancel_requested = Column(Integer, default=0)  # 0=未取消, 1=已请求取消
    # 用户选择的初始大纲章数
    chapter_count = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "status": self.status,
            "progress": self.progress,
            "status_message": self.status_message,
            "world_done": self.world_done,
            "career_done": self.career_done,
            "org_done": self.org_done,
            "characters_done": self.characters_done,
            "assign_careers_done": self.assign_careers_done,
            "relations_done": self.relations_done,
            "assign_org_members_done": self.assign_org_members_done,
            "locations_done": self.locations_done,
            "items_done": self.items_done,
            "outline_done": self.outline_done,
            "validate_done": self.validate_done,
            "failed_step": self.failed_step,
            "error": self.error,
            "chapter_count": self.chapter_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
