"""职业阶段更新服务（#19）。

对标 MuMuAINovel CareerUpdateService。从剧情分析的 character_states[].career_changes
自动更新角色的职业阶段进度。接入 chapter_service._auto_analyze 链路。
"""
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character_career import CharacterCareer
from app.models.career import Career
from app.models.character import Character

logger = logging.getLogger(__name__)


class CareerUpdateService:
    """根据剧情分析更新角色职业阶段。"""

    def __init__(self, db: AsyncSession, project_id: int):
        self.db = db
        self.project_id = project_id

    async def update_from_analysis(
        self,
        character_states: list,
        chapter_id: Optional[int] = None,
        chapter_number: Optional[int] = None,
    ):
        """从 PlotAnalysis.character_states 更新职业阶段。

        character_states 项可能含：
        - character_name / character: 角色名
        - career_changes: {main_career_stage_change: int, sub_career_changes: [...], new_careers: [...]}
        """
        if not character_states:
            return {"updated": 0, "added": 0}

        # 预加载项目角色与职业
        chars = (await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )).scalars().all()
        char_by_name = {c.name: c for c in chars}

        updated = 0
        added = 0
        for state in character_states:
            if not isinstance(state, dict):
                continue
            char_name = state.get("character_name") or state.get("character")
            changes = state.get("career_changes")
            if not char_name or not changes or not isinstance(changes, dict):
                continue
            char = char_by_name.get(char_name)
            if not char:
                continue

            # 1. 主职业阶段变化
            stage_delta = changes.get("main_career_stage_change") or changes.get("stage_change")
            if stage_delta and char.main_career_id:
                cc = (await self.db.execute(
                    select(CharacterCareer).where(
                        CharacterCareer.character_id == char.id,
                        CharacterCareer.career_id == char.main_career_id,
                        CharacterCareer.career_type == "main",
                    )
                )).scalar_one_or_none()
                if cc:
                    new_stage = max(1, cc.current_stage + int(stage_delta))
                    cc.current_stage = new_stage
                    cc.stage_progress = 0
                    if chapter_number:
                        cc.reached_current_stage_at = f"第{chapter_number}章"
                    char.main_career_stage = new_stage
                    updated += 1

            # 2. 新职业
            new_careers = changes.get("new_careers") or []
            if isinstance(new_careers, list):
                for nc in new_careers:
                    if not isinstance(nc, dict):
                        continue
                    career_name = nc.get("name") or nc.get("career")
                    if not career_name:
                        continue
                    career = (await self.db.execute(
                        select(Career).where(
                            Career.project_id == self.project_id,
                            Career.name.like(f"%{career_name}%"),
                        )
                    )).scalar_one_or_none()
                    if not career:
                        continue
                    # 检查是否已存在
                    existing = (await self.db.execute(
                        select(CharacterCareer).where(
                            CharacterCareer.character_id == char.id,
                            CharacterCareer.career_id == career.id,
                        )
                    )).scalar_one_or_none()
                    if existing:
                        continue
                    c_type = nc.get("type", "sub")
                    if c_type not in ("main", "sub"):
                        c_type = "sub"
                    cc = CharacterCareer(
                        project_id=self.project_id,
                        character_id=char.id,
                        career_id=career.id,
                        career_type=c_type,
                        current_stage=1,
                        started_at=f"第{chapter_number}章" if chapter_number else "",
                        source="analysis",
                    )
                    self.db.add(cc)
                    if c_type == "main":
                        char.main_career_id = career.id
                        char.main_career_stage = 1
                    else:
                        subs = char.sub_careers or []
                        subs.append({"career_id": career.id, "name": career.name, "stage": 1})
                        char.sub_careers = subs
                    added += 1

        if updated or added:
            await self.db.commit()
        return {"updated": updated, "added": added}
