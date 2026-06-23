"""剧情分析模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, Float
from app.core.database import Base


class PlotAnalysis(Base):
    __tablename__ = "plot_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    # 分析结果
    hooks = Column(JSON, default=dict)  # 剧情钩子 {suspense, emotional, conflict, cognitive}
    foreshadows = Column(JSON, default=list)  # 伏笔分析 [{type, title, detail, reference_foreshadow_id}]
    conflicts = Column(JSON, default=list)  # 冲突分析 [{type, parties, intensity, progress}]
    conflict_types = Column(JSON, default=list)  # 冲突类型汇总 [人vs人,人vs社会,内心,环境]
    emotion_curve = Column(JSON, default=list)  # 情感曲线 [{point, emotion, intensity}]
    emotional_curve = Column(JSON, default=dict)  # 结构化情感 {start,middle,end,arc_summary}
    character_states = Column(JSON, default=list)  # 角色状态变化
    organization_states = Column(JSON, default=list)  # 组织状态变化 [#14 增强]
    key_plot_points = Column(JSON, default=list)  # 关键情节点
    scenes = Column(JSON, default=list)  # 场景与节奏
    # 节奏与占比 [#14 增强]
    plot_stage = Column(String(20), default="")  # 开端/发展/高潮/结局/过渡
    dialogue_ratio = Column(Float, default=0)  # 对话占比 0-1
    description_ratio = Column(Float, default=0)  # 描写占比 0-1
    pacing = Column(String(20), default="")  # 节奏 fast/medium/slow
    quality_scores = Column(JSON, default=dict)  # {pacing, engagement, coherence, writing_quality, character_depth, dialogue_quality, world_consistency, plot_logic, overall}
    consistency_issues = Column(JSON, default=list)  # 一致性问题列表
    suggestions = Column(JSON, default=list)  # 改进建议
    raw_response = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "chapter_id": self.chapter_id,
            "chapter_number": self.chapter_number,
            "hooks": self.hooks or {},
            "foreshadows": self.foreshadows or [],
            "conflicts": self.conflicts or [],
            "conflict_types": self.conflict_types or [],
            "emotion_curve": self.emotion_curve or [],
            "emotional_curve": self.emotional_curve or {},
            "character_states": self.character_states or [],
            "organization_states": self.organization_states or [],
            "key_plot_points": self.key_plot_points or [],
            "scenes": self.scenes or [],
            "plot_stage": self.plot_stage or "",
            "dialogue_ratio": self.dialogue_ratio or 0,
            "description_ratio": self.description_ratio or 0,
            "pacing": self.pacing or "",
            "quality_scores": self.quality_scores or {},
            "suggestions": self.suggestions or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }