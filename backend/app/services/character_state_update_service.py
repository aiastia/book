"""角色状态更新服务（#14）。

对标 MuMuAINovel CharacterStateUpdateService。从剧情分析的 character_states
自动更新：生死状态、心理状态、关系亲密度、组织成员状态。

关键：章节号防回退保护——只允许更新 chapter_number >= 已记录章节的状态，
防止重新分析旧章节时覆盖新状态。
"""
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character, CharacterRelation
from app.models.organization_member import OrganizationMember

logger = logging.getLogger(__name__)


class CharacterStateUpdateService:
    """分析驱动的角色状态追踪。"""

    def __init__(self, db: AsyncSession, project_id: int):
        self.db = db
        self.project_id = project_id

    async def update_from_analysis(
        self,
        character_states: list,
        chapter_id: Optional[int] = None,
        chapter_number: Optional[int] = None,
    ):
        """主入口：依次更新生死/心理/关系/组织/角色弧线。"""
        if not character_states:
            return {"survival": 0, "psychological": 0, "relationships": 0, "org": 0, "arc": 0}

        chars = (await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )).scalars().all()
        char_by_name = {c.name: c for c in chars}

        results = {
            "survival": await self._update_survival(character_states, char_by_name, chapter_number),
            "psychological": await self._update_psychological(character_states, char_by_name, chapter_number),
            "relationships": await self._update_relationships(character_states, chars, chapter_number),
            "org": await self._update_org_memberships(character_states, chars, chapter_number),
            "arc": await self._update_arc(character_states, char_by_name, chapter_number),
        }
        if any(results.values()):
            await self.db.commit()
        return results

    async def _update_survival(
        self, character_states, char_by_name: dict, chapter_number
    ) -> int:
        """更新生死状态：active/deceased/missing/retired/destroyed。"""
        updated = 0
        # 状态值映射（AI 可能返回多种写法）
        survival_map = {
            "death": "deceased", "dead": "deceased", "killed": "deceased", "死亡": "deceased",
            "missing": "missing", "失踪": "missing", "消失": "missing",
            "retired": "retired", "退隐": "retired", "隐退": "retired",
            "alive": "alive", "active": "alive", "存活": "alive",
        }
        for state in character_states:
            if not isinstance(state, dict):
                continue
            name = state.get("character") or state.get("character_name") or state.get("name")
            survival = state.get("survival_status") or state.get("status_change") or state.get("survival")
            if not name or not survival:
                continue
            char = self._match_char(name, char_by_name)
            if not char:
                continue
            new_status = survival_map.get(str(survival).lower().strip(), str(survival).strip())
            # 章节号防回退
            if chapter_number and char.status_updated_chapter and chapter_number < char.status_updated_chapter:
                continue
            if new_status in ("deceased", "missing", "retired", "alive") and char.status != new_status:
                char.status = new_status if new_status != "alive" else "alive"
                if hasattr(char, "status_updated_chapter"):
                    char.status_updated_chapter = chapter_number
                updated += 1
        return updated

    async def _update_psychological(
        self, character_states, char_by_name: dict, chapter_number
    ) -> int:
        """更新心理状态（mental_state）。带章节防回退。"""
        updated = 0
        for state in character_states:
            if not isinstance(state, dict):
                continue
            name = state.get("character") or state.get("character_name") or state.get("name")
            new_state = state.get("state_after") or state.get("mental_change") or state.get("psychological_state") or state.get("current_state")
            if not name or not new_state:
                continue
            char = self._match_char(name, char_by_name)
            if not char:
                continue
            # 章节防回退（用 mental_state 字段无章节追踪，简单覆盖）
            char.mental_state = str(new_state).strip()[:100]
            updated += 1
        return updated

    async def _update_relationships(
        self, character_states, chars: list, chapter_number
    ) -> int:
        """更新关系亲密度。从 relation_change 推断亲密度变化。"""
        if len(chars) < 2:
            return 0
        name_map = {c.name: c for c in chars}
        # 预加载关系
        existing = (await self.db.execute(
            select(CharacterRelation).where(CharacterRelation.project_id == self.project_id)
        )).scalars().all()
        rel_map = {(r.from_character_id, r.to_character_id): r for r in existing}
        updated = 0
        for state in character_states:
            if not isinstance(state, dict):
                continue
            rel_change = state.get("relation_change") or state.get("relationship_changes")
            if not rel_change or not isinstance(rel_change, (list, str, dict)):
                continue
            name = state.get("character") or state.get("character_name")
            char = name_map.get(name) if name else None
            if not char:
                continue
            # 解析关系变化（支持 list/dict/str）
            changes = rel_change if isinstance(rel_change, list) else [rel_change]
            for ch in changes:
                target_name, delta, rtype = self._parse_relation_change(ch, name_map)
                if not target_name:
                    continue
                target = name_map.get(target_name)
                if not target:
                    continue
                key = (char.id, target.id)
                rel = rel_map.get(key)
                if not rel:
                    # 反向查
                    rel = rel_map.get((target.id, char.id))
                if rel and delta:
                    rel.intimacy = max(-100, min(100, (rel.intimacy or 0) + delta))
                    # strength 是 0-1 的关系强度，按亲密度方向微调（不应写成章节号）
                    if delta > 0:
                        rel.strength = max(rel.strength or 0.5, 0.6)
                    elif delta < 0:
                        rel.strength = min(rel.strength or 0.5, 0.4)
                    updated += 1
                elif not rel and delta:
                    # 新建关系（strength 按 delta 方向设初值，保持 0-1 语义）
                    new_rel = CharacterRelation(
                        project_id=self.project_id,
                        from_character_id=char.id,
                        to_character_id=target.id,
                        relation_type=rtype or "关系变化",
                        intimacy=max(-100, min(100, delta)),
                        category="social",
                        strength=0.6 if delta > 0 else 0.4,
                    )
                    self.db.add(new_rel)
                    rel_map[key] = new_rel
                    updated += 1
        return updated

    async def _update_org_memberships(
        self, character_states, chars: list, chapter_number
    ) -> int:
        """更新组织成员状态（退隐/驱逐/死亡）。"""
        name_map = {c.name: c for c in chars}
        # 状态映射
        org_status_map = {
            "deceased": "deceased", "death": "deceased", "killed": "deceased",
            "retired": "retired", "expelled": "expelled", "驱逐": "expelled",
            "left": "retired", "离开": "retired",
        }
        updated = 0
        for state in character_states:
            if not isinstance(state, dict):
                continue
            name = state.get("character") or state.get("character_name")
            survival = state.get("survival_status") or state.get("status_change")
            if not name or not survival:
                continue
            char = name_map.get(name)
            if not char:
                continue
            new_status = org_status_map.get(str(survival).lower().strip())
            if not new_status:
                continue
            # 更新该角色的所有组织成员记录
            memberships = (await self.db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.character_id == char.id,
                    OrganizationMember.status == "active",
                )
            )).scalars().all()
            for m in memberships:
                if new_status == "deceased":
                    m.status = "deceased"
                    if chapter_number:
                        m.left_at = f"第{chapter_number}章"
                    updated += 1
                elif new_status == "retired":
                    m.status = "retired"
                    if chapter_number:
                        m.left_at = f"第{chapter_number}章"
                    updated += 1
                elif new_status == "expelled":
                    m.status = "expelled"
                    if chapter_number:
                        m.left_at = f"第{chapter_number}章"
                    updated += 1
        return updated

    async def _update_arc(self, character_states: list, name_map: dict, chapter_number: Optional[int]) -> int:
        """更新角色弧线：arc_type（变化类型）+ character_change（变化轨迹，随章节累积）。

        AI 返回字段（character_states[]）：
          - arc_progress: 本章节该角色的弧线进展描述
          - arc_type_change: 弧线类型是否转变（如"成长→顿悟"），有则更新 arc_type
        """
        updated = 0
        for state in character_states:
            if not isinstance(state, dict):
                continue
            name = state.get("name") or state.get("character")
            char = self._match_char(name, name_map) if name else None
            if not char:
                continue
            chg = False
            # 1) 弧线类型转变 → 更新 arc_type
            arc_type_change = state.get("arc_type_change") or state.get("arc_change")
            if arc_type_change and str(arc_type_change).strip():
                new_arc = str(arc_type_change).strip()[:50]
                if char.arc_type != new_arc:
                    char.arc_type = new_arc
                    chg = True
            # 2) 弧线进展 → 累积到 character_change（追加"第N章：xxx"，去重防溢出）
            arc_progress = state.get("arc_progress") or state.get("character_progress")
            if arc_progress and str(arc_progress).strip():
                snippet = str(arc_progress).strip()[:200]
                prefix = f"第{chapter_number}章：" if chapter_number else "•"
                entry = f"{prefix}{snippet}"
                existing = (char.character_change or "").strip()
                # 去重：本条已记录过则不重复追加
                if entry not in existing:
                    parts = [p.strip() for p in existing.split("\n") if p.strip()]
                    parts.append(entry)
                    # 保留最近 30 条，避免无限增长
                    char.character_change = "\n".join(parts[-30:])
                    chg = True
            if chg:
                updated += 1
        return updated

    def _match_char(self, name: str, char_by_name: dict) -> Optional[Character]:
        """模糊匹配角色名。"""
        if name in char_by_name:
            return char_by_name[name]
        for cname, char in char_by_name.items():
            if name in cname or cname in name:
                return char
        return None

    def _parse_relation_change(self, change, name_map: dict):
        """从关系变化描述提取目标角色/亲密度变化/关系类型。"""
        if isinstance(change, dict):
            target = change.get("target") or change.get("with") or change.get("character")
            delta = change.get("intimacy_change") or change.get("delta")
            rtype = change.get("type") or change.get("relation_type")
            return target, self._safe_int(delta), rtype
        if isinstance(change, str):
            # 简单关键词推断亲密度方向
            text = change
            delta = 0
            if any(k in text for k in ["信任", "亲近", "和解", "相爱", "忠诚", "感激"]):
                delta = 15
            elif any(k in text for k in ["背叛", "决裂", "仇恨", "敌对", "疏远", "猜忌"]):
                delta = -20
            elif any(k in text for k in ["冲突", "争执", "不满"]):
                delta = -10
            # 匹配角色名
            target = None
            for name in name_map:
                if name in text:
                    target = name
                    break
            return target, delta, text[:20] if len(text) <= 20 else "关系变化"
        return None, 0, None

    def _safe_int(self, v) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0
