"""组织模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    org_type = Column(String(50), default="")  # 宗门/家族/国家/商会/帮派
    description = Column(Text, default="")
    hierarchy = Column(JSON, default=list)  # [{level, title, character_ids}]
    members = Column(JSON, default=list)  # [{character_id, role, joined_chapter}]
    relations = Column(JSON, default=list)  # [{org_id, relation_type, description}]
    territory = Column(Text, default="")  # 势力范围
    power_level = Column(String(50), default="")  # 势力等级（文本，兼容旧数据）
    # 组织树层级（#18 增强）
    parent_org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)  # 自引用，null=顶级
    tree_level = Column(Integer, default=0)  # 层级深度 0=顶级
    power_value = Column(Integer, default=50)  # 势力数值 0-100
    member_count = Column(Integer, default=0)  # 成员数（冗余，便于排序）
    location = Column(String(200), default="")  # 所在地
    motto = Column(String(200), default="")  # 宗旨/口号
    color = Column(String(20), default="")  # 代表色
    status = Column(String(20), default="active")  # active/dissolved/hidden
    structure = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)