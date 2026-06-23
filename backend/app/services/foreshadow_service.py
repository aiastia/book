"""伏笔管理服务"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.foreshadow import Foreshadow
from app.core.config import settings


class ForeshadowService:
    def __init__(self, db: AsyncSession, project_id: int):
        self.db = db
        self.project_id = project_id

    async def create(self, data: dict) -> Foreshadow:
        fs = Foreshadow(project_id=self.project_id, **data)
        self.db.add(fs)
        await self.db.commit()
        await self.db.refresh(fs)
        return fs

    async def get(self, foreshadow_id: int) -> Optional[Foreshadow]:
        result = await self.db.execute(
            select(Foreshadow).where(
                Foreshadow.id == foreshadow_id,
                Foreshadow.project_id == self.project_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self, status: str = None) -> list[Foreshadow]:
        q = select(Foreshadow).where(Foreshadow.project_id == self.project_id)
        if status:
            q = q.where(Foreshadow.status == status)
        q = q.order_by(Foreshadow.created_at.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def update(self, foreshadow_id: int, data: dict) -> Optional[Foreshadow]:
        fs = await self.get(foreshadow_id)
        if not fs:
            return None
        for key, value in data.items():
            if hasattr(fs, key):
                setattr(fs, key, value)
        await self.db.commit()
        await self.db.refresh(fs)
        return fs

    async def delete(self, foreshadow_id: int) -> bool:
        fs = await self.get(foreshadow_id)
        if not fs:
            return False
        await self.db.delete(fs)
        await self.db.commit()
        return True

    # === 伏笔注入相关方法 ===

    async def get_must_resolve_foreshadows(self, chapter_number: int) -> list[Foreshadow]:
        """获取本章必须回收的伏笔（target_resolve_chapter_number == chapter_number 且 status=planted）"""
        result = await self.db.execute(
            select(Foreshadow).where(
                Foreshadow.project_id == self.project_id,
                Foreshadow.status == "planted",
                Foreshadow.target_resolve_chapter_number == chapter_number,
            )
        )
        return list(result.scalars().all())

    async def get_pending_resolve_foreshadows(self, chapter_number: int, lookahead: int = None) -> list[Foreshadow]:
        """获取即将到期的伏笔（未来 lookahead 章内需回收）"""
        lookahead = lookahead or settings.FORESHADOW_LOOKAHEAD
        result = await self.db.execute(
            select(Foreshadow).where(
                Foreshadow.project_id == self.project_id,
                Foreshadow.status == "planted",
                Foreshadow.target_resolve_chapter_number > chapter_number,
                Foreshadow.target_resolve_chapter_number <= chapter_number + lookahead,
            )
        )
        return list(result.scalars().all())

    async def get_overdue_foreshadows(self, chapter_number: int) -> list[Foreshadow]:
        """获取超期未回收的伏笔"""
        result = await self.db.execute(
            select(Foreshadow).where(
                Foreshadow.project_id == self.project_id,
                Foreshadow.status == "planted",
                Foreshadow.target_resolve_chapter_number < chapter_number,
            )
        )
        return list(result.scalars().all())

    async def get_pending_plant_foreshadows(self, chapter_number: int) -> list[Foreshadow]:
        """获取本章应埋入的伏笔（plant_chapter_number == chapter_number 且 status=pending）"""
        result = await self.db.execute(
            select(Foreshadow).where(
                Foreshadow.project_id == self.project_id,
                Foreshadow.status == "pending",
                Foreshadow.plant_chapter_number == chapter_number,
            )
        )
        return list(result.scalars().all())

    async def get_foreshadow_reminders(self, chapter_number: int) -> str:
        """构建伏笔回收+埋入提醒文本"""
        parts = []

        # 1. 本章必须回收的伏笔
        must_resolve = await self.get_must_resolve_foreshadows(chapter_number)
        if must_resolve:
            lines = ["🎯 【本章必须回收的伏笔】"]
            for fs in must_resolve:
                lines.append(f"  - {fs.title}: {fs.content}")
            parts.append("\n".join(lines))

        # 2. 即将到期的伏笔
        pending_resolve = await self.get_pending_resolve_foreshadows(chapter_number)
        if pending_resolve:
            lines = ["⏰ 【即将到期伏笔】"]
            for fs in pending_resolve:
                lines.append(f"  - 第{fs.target_resolve_chapter_number}章前需回收: {fs.title} - {fs.content}")
            parts.append("\n".join(lines))

        # 3. 超期未回收的伏笔
        overdue = await self.get_overdue_foreshadows(chapter_number)
        if overdue:
            lines = ["⚠️ 【超期未回收伏笔】"]
            for fs in overdue:
                lines.append(f"  - {fs.title}（第{fs.actual_plant_chapter or '?'}章埋入，已超期）: {fs.content}")
            parts.append("\n".join(lines))

        # 4. 本章应埋入的伏笔（新增！）
        pending_plant = await self.get_pending_plant_foreshadows(chapter_number)
        if pending_plant:
            lines = ["🌱 【本章应埋入的伏笔】"]
            for fs in pending_plant:
                lines.append(f"  - {fs.title}: {fs.content}（计划在第{fs.plant_chapter_number}章埋入，第{fs.target_resolve_chapter_number or '?'}章回收）")
            parts.append("\n".join(lines))

        return "\n\n".join(parts) if parts else "暂无伏笔提醒"

    async def auto_plant_pending_foreshadows(self, chapter_number: int) -> list[Foreshadow]:
        """自动将指定本章的 pending 伏笔标记为 planted"""
        foreshadows = await self.get_pending_plant_foreshadows(chapter_number)
        planted = []
        for fs in foreshadows:
            fs.status = "planted"
            fs.actual_plant_chapter = chapter_number
            planted.append(fs)
        if planted:
            await self.db.commit()
        return planted

    async def auto_update_from_analysis(self, analysis_result: dict, chapter_number: int):
        """根据剧情分析结果自动更新伏笔状态"""
        foreshadows_data = analysis_result.get("foreshadows", [])

        for fs_data in foreshadows_data:
            fs_type = fs_data.get("type", "")
            title = fs_data.get("title", "")
            # 字段兼容：detail / content / description 都接受
            detail = fs_data.get("detail") or fs_data.get("content") or fs_data.get("description") or ""
            ref_id = fs_data.get("reference_foreshadow_id")
            fs_subtype = fs_data.get("foreshadow_type", "")
            importance = fs_data.get("importance") or fs_data.get("priority") or 5
            target_resolve = fs_data.get("target_resolve_chapter_number")

            if fs_type == "planted":
                if ref_id:
                    # 匹配已有伏笔
                    fs = await self.get(ref_id)
                    if fs and fs.status == "pending":
                        fs.status = "planted"
                        fs.actual_plant_chapter = chapter_number
                else:
                    # 查找是否有标题匹配的 pending 伏笔
                    all_pending = await self.list_all(status="pending")
                    matched = None
                    for p in all_pending:
                        if p.title == title or (title and title in p.title):
                            matched = p
                            break
                    if matched:
                        matched.status = "planted"
                        matched.actual_plant_chapter = chapter_number
                        # 补全缺失字段（之前创建时遗漏的）
                        if detail and not matched.content:
                            matched.content = detail
                        if fs_subtype and not matched.foreshadow_type:
                            matched.foreshadow_type = fs_subtype
                        if target_resolve and not matched.target_resolve_chapter_number:
                            matched.target_resolve_chapter_number = target_resolve
                    else:
                        # 创建新的分析发现伏笔（补全所有字段，避免空内容）
                        create_data = {
                            "title": title or "（未命名伏笔）",
                            "content": detail,
                            "status": "planted",
                            "source_type": "analysis",
                            "actual_plant_chapter": chapter_number,
                            "plant_chapter_number": chapter_number,
                            "priority": importance,
                        }
                        if fs_subtype:
                            create_data["foreshadow_type"] = fs_subtype
                        if target_resolve:
                            create_data["target_resolve_chapter_number"] = target_resolve
                        await self.create(create_data)

            elif fs_type == "resolved":
                if ref_id:
                    fs = await self.get(ref_id)
                    if fs and fs.status == "planted":
                        fs.status = "resolved"
                        fs.actual_resolve_chapter = chapter_number
                else:
                    # 尝试匹配
                    all_planted = await self.list_all(status="planted")
                    for p in all_planted:
                        if p.title == title or (title and title in p.title):
                            p.status = "resolved"
                            p.actual_resolve_chapter = chapter_number
                            break

        await self.db.commit()

    async def plan_foreshadows_from_outlines(self, ai_client, outlines_data: str, characters_info: str, user_id: int = None) -> list[dict]:
        """AI 根据大纲自动规划伏笔"""
        from app.skills.engine import SkillEngine
        engine = SkillEngine(self.db, user_id)
        result = await engine.execute_skill(
            "foreshadow_plan",
            ai_client,
            context={
                "outlines": outlines_data,
                "existing_foreshadows": str([f.title for f in await self.list_all()]),
                "characters_info": characters_info,
                "user_prompt": "请根据以上大纲信息，规划伏笔。",
            },
        )
        if result.get("error"):
            return []
        planned = result.get("json", [])
        if not isinstance(planned, list):
            return []
        # 自动创建规划的伏笔
        created = []
        for item in planned:
            fs = await self.create({
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "foreshadow_type": item.get("foreshadow_type", ""),
                "status": "pending",
                "source_type": "planned",
                "plant_chapter_number": item.get("plant_chapter_number"),
                "target_resolve_chapter_number": item.get("target_resolve_chapter_number"),
                "priority": item.get("priority", 5),
            })
            created.append({
                "id": fs.id,
                "title": fs.title,
                "content": fs.content,
                "foreshadow_type": fs.foreshadow_type,
                "plant_chapter_number": fs.plant_chapter_number,
                "target_resolve_chapter_number": fs.target_resolve_chapter_number,
                "priority": fs.priority,
            })
        return created

    # ===== #15 伏笔闭环操作 =====

    async def mark_as_planted(
        self, foreshadow_id: int, chapter_number: int, hint_text: str = ""
    ) -> Optional[Foreshadow]:
        """标记伏笔为已埋入。"""
        fs = await self.get(foreshadow_id)
        if not fs:
            return None
        fs.status = "planted"
        fs.actual_plant_chapter = chapter_number
        if hint_text:
            fs.content = (fs.content or "") + f"\n[埋入提示：{hint_text}]"
        await self.db.commit()
        return fs

    async def mark_as_resolved(
        self, foreshadow_id: int, chapter_number: int,
        resolution_text: str = "", is_partial: bool = False,
    ) -> Optional[Foreshadow]:
        """标记伏笔为已回收。is_partial=True 时标记为 partially_resolved。"""
        fs = await self.get(foreshadow_id)
        if not fs:
            return None
        fs.status = "partially_resolved" if is_partial else "resolved"
        fs.actual_resolve_chapter = chapter_number
        if resolution_text:
            fs.resolution_text = resolution_text if hasattr(fs, "resolution_text") else resolution_text
        await self.db.commit()
        return fs

    async def mark_as_abandoned(
        self, foreshadow_id: int, reason: str = ""
    ) -> Optional[Foreshadow]:
        """放弃伏笔。"""
        fs = await self.get(foreshadow_id)
        if not fs:
            return None
        fs.status = "abandoned"
        if reason and hasattr(fs, "abandon_reason"):
            fs.abandon_reason = reason
        await self.db.commit()
        return fs

    def get_urgency_level(self, fs: Foreshadow, current_chapter: int) -> int:
        """计算伏笔紧急度：0不紧急/1需关注/2急需/3已超期。"""
        if fs.status in ("resolved", "abandoned"):
            return 0
        if fs.status == "pending":
            return 1
        # planted 状态看是否超期
        if fs.target_resolve_chapter_number:
            if fs.target_resolve_chapter_number < current_chapter:
                return 3  # 超期
            elif fs.target_resolve_chapter_number <= current_chapter:
                return 2  # 本章需回收
            elif fs.target_resolve_chapter_number - current_chapter <= 3:
                return 1  # 即将到期
        return 0

    async def sync_from_analysis(
        self, project_id: int, chapter_ids: list[int] = None, db: AsyncSession = None
    ) -> dict:
        """从多个章节的剧情分析批量同步伏笔状态。"""
        from app.models.plot_analysis import PlotAnalysis
        session = db or self.db
        q = select(PlotAnalysis).where(PlotAnalysis.project_id == project_id)
        if chapter_ids:
            q = q.where(PlotAnalysis.chapter_id.in_(chapter_ids))
        analyses = (await session.execute(q)).scalars().all()
        planted = resolved = 0
        for a in analyses:
            for fs_data in (a.foreshadows or []):
                if not isinstance(fs_data, dict):
                    continue
                fs_type = fs_data.get("type", "")
                ref_id = fs_data.get("reference_foreshadow_id")
                title = fs_data.get("title", "")
                if fs_type == "planted" and ref_id:
                    fs = await self.get(ref_id)
                    if fs and fs.status == "pending":
                        await self.mark_as_planted(fs.id, a.chapter_number)
                        planted += 1
                elif fs_type == "resolved" and ref_id:
                    fs = await self.get(ref_id)
                    if fs and fs.status == "planted":
                        await self.mark_as_resolved(fs.id, a.chapter_number)
                        resolved += 1
        return {"synced": True, "planted": planted, "resolved": resolved, "analyses": len(analyses)}

    async def build_chapter_context(self, chapter_number: int) -> str:
        """为章节生成注入分层伏笔提醒（对标 MuMu build_chapter_context）。

        分层策略：
        1. 必须回收（target==当前章）→ 强制要求
        2. 超期未回收 → 强调
        3. 即将到期（3章内）→ 提醒（禁止提前回收）
        4. 本章应埋入 → 引导
        """
        return await self.get_foreshadow_reminders(chapter_number)