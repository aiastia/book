"""角色模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, Float
from app.core.database import Base


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    # ---- 基本信息 ----
    name = Column(String(100), nullable=False)
    role = Column(String(50), default="配角")  # 主角/配角/反派/路人
    gender = Column(String(10), default="")
    age = Column(String(20), default="")
    identity = Column(String(200), default="")  # 身份（如：武林盟主之女/失忆的天才少年）

    # ---- 外貌与性格 ----
    appearance = Column(Text, default="")  # 外貌特征（详细）
    personality = Column(Text, default="")  # 性格特点（优点+缺点）

    # ---- 背景与成长 ----
    background = Column(Text, default="")  # 成长背景/身世
    growth_experience = Column(Text, default="")  # 成长经历（关键转折点）
    ability = Column(Text, default="")  # 能力/技能

    # ---- 动机与目标 ----
    story_goal = Column(Text, default="")  # 故事中的目标
    motivation = Column(Text, default="")  # 内在动机（为什么追求这个目标）
    weakness = Column(Text, default="")  # 弱点/缺陷

    # ---- 变化与弧线 ----
    arc_type = Column(String(50), default="")  # 人物变化类型（成长/堕落/救赎/顿悟/平淡）
    character_change = Column(Text, default="")  # 人物变化（开篇→结局的转变）
    speech_style = Column(String(200), default="")  # 说话风格特征

    # ---- 状态 ----
    status = Column(String(20), default="alive")  # alive/dead/missing/unknown
    mental_state = Column(String(50), default="")  # 当前心理状态

    # ---- 关系与归属 ----
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    relationships = Column(JSON, default=list)  # [{character_id, relation_type, description}]
    tags = Column(JSON, default=list)  # 特征标签

    # ---- 扩展 ----
    occupation_detail = Column(JSON, default=dict)  # 职业阶段体系
    structure = Column(JSON, default=dict)  # JSON 扩展数据
    # 职业关联（#19 增强，冗余字段便于展示）
    main_career_id = Column(Integer, nullable=True)  # 主职业 ID（关联 careers 表）
    main_career_stage = Column(Integer, default=0)  # 主职业当前阶段（旧，保留兼容）
    main_career_stage_desc = Column(String(200), default="")  # 主职业境界文字描述（如：已臻化境、初窥门径）
    sub_careers = Column(JSON, default=list)  # [{career_id, name, stage_desc}]
    # 状态追踪章节号（#14 防回退保护）
    status_updated_chapter = Column(Integer, nullable=True)  # 生死状态最后更新的章节
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CharacterRelation(Base):
    """角色关系：A 对 B 的关系（有向）。用于关系图谱查询与自动维护。"""
    __tablename__ = "character_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    from_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    to_character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, default="相识")  # 恋人/师徒/敌对/同门/上下级
    # 分类：family(亲情) / social(社交) / hostile(敌对) / professional(职业) / romantic(情感)
    category = Column(String(20), default="social")
    intimacy = Column(Integer, default=0)  # 亲密度 -100~100（负=敌对，正=亲密）
    strength = Column(Float, default=0.5)  # 关系强度 0-1（向后兼容）
    status = Column(String(20), default="active")  # active/past/broken/complicated
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self, from_name=None, to_name=None):
        """序列化，附带角色名方便前端渲染图谱"""
        return {
            "id": self.id, "project_id": self.project_id,
            "from_character_id": self.from_character_id,
            "to_character_id": self.to_character_id,
            "from_name": from_name, "to_name": to_name,
            "relation_type": self.relation_type, "category": self.category,
            "intimacy": self.intimacy, "strength": self.strength,
            "status": self.status, "description": self.description,
        }