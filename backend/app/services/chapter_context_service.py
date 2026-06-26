"""章节上下文构建服务"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.character import Character
from app.models.story_memory import StoryMemory
from app.models.plot_analysis import PlotAnalysis
from app.models.project import Project
from app.services.foreshadow_service import ForeshadowService
from app.core.config import settings
from app.core.ai_client import AIClient


class ChapterContextService:
    """构建章节生成所需的完整上下文"""

    def __init__(self, db: AsyncSession, project_id: int, user_id: int = None):
        self.db = db
        self.project_id = project_id
        self.user_id = user_id
        self.foreshadow_service = ForeshadowService(db, project_id)

    async def build_chapter_context(self, chapter: Chapter, project: Project) -> dict:
        """构建完整的章节上下文"""
        context = {}

        # P0-核心信息
        context.update(await self._get_core_context(chapter, project))

        # 世界设定（核心世界观 + 详细设定，对标原项目注入）
        context.update(await self._get_world_context())

        # P1-重要信息
        context.update(await self._get_important_context(chapter))

        # P2-参考信息
        context.update(await self._get_reference_context(chapter))

        # 向量记忆召回（语义相关记忆注入，对标 MuMu memory_service.build_context_for_generation）
        context.update(await self._get_vector_memory_context(chapter))

        # 物品/地点上下文（#1 #2 增强）
        context.update(await self._get_item_location_context(chapter))

        # 卷摘要上下文（方案 A：分层摘要链，保障长期连贯性）
        context.update(await self._get_volume_summaries(chapter))

        # P3-评分反馈
        context.update(await self._get_quality_context(chapter))

        return context

    async def _get_item_location_context(self, chapter: Chapter) -> dict:
        """动态注入本章涉及的物品 + 地点 + 组织。

        策略（动态优先 + 硬上限兜底）：
        1. 从本章大纲/expansion_plan 提取涉及的名称
        2. 优先注入名称匹配的物品/地点（本章确实涉及的）
        3. 补充关键物品/重要地点（即使本章未直接涉及，但影响主线）
        4. 硬截断防膨胀
        """
        out = {}
        try:
            from app.models.item import Item
            from app.models.location import Location

            # 1. 提取本章涉及的关键词（从大纲/扩展计划）
            chapter_keywords = set()
            outline = None
            if chapter.outline_id:
                outline = (await self.db.execute(select(Outline).where(Outline.id == chapter.outline_id))).scalar_one_or_none()
            if not outline:
                outline = (await self.db.execute(
                    select(Outline).where(Outline.project_id == self.project_id, Outline.chapter_number == chapter.chapter_number)
                    .order_by(Outline.id.desc())
                )).scalars().first()
            if outline:
                # 大纲标题、梗概、关键点里的词
                for text in [outline.title or "", outline.summary or ""]:
                    chapter_keywords.update(text.replace("，", " ").replace("。", " ").split())
                for kp in (outline.key_points or []):
                    if isinstance(kp, str):
                        chapter_keywords.update(kp.replace("，", " ").split())
            if chapter.expansion_plan and isinstance(chapter.expansion_plan, dict):
                for ke in (chapter.expansion_plan.get("key_events") or []):
                    if isinstance(ke, str):
                        chapter_keywords.update(ke.replace("，", " ").split())

            # 2. 物品：动态优先
            all_items = (await self.db.execute(
                select(Item).where(Item.project_id == self.project_id)
            )).scalars().all()
            # 分层：本章涉及的 > 关键道具 > 其他
            involved_items = [i for i in all_items if any(kw in i.name for kw in chapter_keywords) or i.name in chapter_keywords]
            key_items = [i for i in all_items if i.is_key_item and i not in involved_items]
            other_items = [i for i in all_items if i not in involved_items and i not in key_items]
            # 组合：涉及的（全量）+ 关键道具（补到8个）+ 其他（补到10个）
            selected_items = involved_items[:8]
            for i in key_items:
                if len(selected_items) >= 8: break
                selected_items.append(i)
            if len(selected_items) < 10:
                for i in other_items:
                    if len(selected_items) >= 10: break
                    selected_items.append(i)
            if selected_items:
                lines = []
                for i in selected_items:
                    tag = "⭐" if i.is_key_item else ""
                    lines.append(f"- {tag}{i.name}（{i.rarity}，{i.item_type}）：{(i.description or '')[:60]}")
                out["key_items"] = "物品：\n" + "\n".join(lines)

            # 3. 地点：动态优先（同策略）
            all_locs = (await self.db.execute(
                select(Location).where(Location.project_id == self.project_id)
            )).scalars().all()
            involved_locs = [l for l in all_locs if any(kw in l.name for kw in chapter_keywords) or l.name in chapter_keywords]
            major_locs = [l for l in all_locs if l.importance in ("major", "key") and l not in involved_locs]
            other_locs = [l for l in all_locs if l not in involved_locs and l not in major_locs]
            selected_locs = involved_locs[:5]
            for l in major_locs:
                if len(selected_locs) >= 6: break
                selected_locs.append(l)
            if len(selected_locs) < 8:
                for l in other_locs:
                    if len(selected_locs) >= 8: break
                    selected_locs.append(l)
            if selected_locs:
                lines = [f"- {l.name}（{l.location_type}）：{(l.atmosphere or l.description or '')[:60]}" for l in selected_locs]
                out["key_locations"] = "地点：\n" + "\n".join(lines)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[context] 物品/地点注入失败（不影响生成）: {e}")
        return out

    async def _get_vector_memory_context(self, chapter: Chapter) -> dict:
        """从向量库召回语义相关记忆，注入章节生成上下文。

        5 路融合检索（最近章节/语义相关/角色相关/重要情节/伏笔），
        召回的记忆作为「故事前情」让 AI 保持连贯。
        失败/无向量库时静默跳过，不影响章节生成。
        """
        if not self.user_id:
            return {}
        try:
            from app.services.memory_vector_service import MemoryVectorService
            from sqlalchemy import select as _sel
            # 检查项目是否有已向量化的记忆（无则跳过，避免空查询）
            has_vec = await self.db.scalar(_sel(func.count(StoryMemory.id)).where(
                StoryMemory.project_id == self.project_id,
                StoryMemory.vector_id != "",
            ))
            if not has_vec:
                return {}
            ai_client = await AIClient.from_user_config(self.db, self.user_id)
            vs = MemoryVectorService(ai_client)
            # 取本章大纲作为语义 query
            outline_text = ""
            if chapter.outline_id:
                ol = (await self.db.execute(_sel(Outline).where(Outline.id == chapter.outline_id))).scalar_one_or_none()
                if ol:
                    outline_text = (ol.summary or ol.title or "")[:500]
            # 取本章出场角色名作为角色 query
            char_names = ""
            try:
                chs = chapter.characters or []
                if isinstance(chs, list):
                    char_names = " ".join(str(c) for c in chs[:8])
            except Exception:
                pass
            recalled = await vs.build_context_for_generation(
                user_id=self.user_id, project_id=self.project_id,
                current_chapter=chapter.chapter_number or 1,
                chapter_outline=outline_text,
                character_names=char_names,
                top_k=3,
            )
            if recalled:
                return {"recalled_memories": recalled}
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[context] 向量记忆召回失败（不影响生成）: {e}")
        return {}

    async def _get_volume_summaries(self, chapter: Chapter) -> dict:
        """卷摘要注入（方案 A：分层摘要链）。

        查询所有已完成的卷摘要（memory_type='volume_summary'），
        按章节号正序注入上下文，让 AI 了解长期剧情脉络。
        卷摘要覆盖 10 章之外的长期连贯性，弥补摘要链滑动窗口的不足。
        """
        try:
            vol_summaries = (await self.db.execute(
                select(StoryMemory).where(
                    StoryMemory.project_id == self.project_id,
                    StoryMemory.memory_type == "volume_summary",
                    StoryMemory.chapter_number < chapter.chapter_number,
                ).order_by(StoryMemory.chapter_number)
            )).scalars().all()

            if not vol_summaries:
                return {}

            parts = []
            for vs in vol_summaries:
                title = vs.title or f"第{vs.chapter_number}章前卷摘要"
                parts.append(f"【{title}】{vs.content}")

            # 全书主线脉络（如果有 3+ 卷，再加一层压缩）
            if len(parts) >= 3:
                # 将所有卷摘要压缩为"全书脉络"提示
                all_arcs = " → ".join(
                    vs.content[:50] + "…" for vs in vol_summaries[-5:]  # 最近 5 卷的浓缩
                )
                parts.append(f"【全书主线脉络（近5卷演进）】{all_arcs}")

            return {"volume_summaries": "\n\n".join(parts)}
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[context] 卷摘要加载失败（不影响生成）: {e}")
        return {}

    async def _get_world_context(self) -> dict:
        """世界设定上下文：核心世界观（时间/地点/氛围/规则）+ 详细设定条目。

        让章节生成时 AI 知道故事发生在什么世界，避免设定断层。
        """
        from app.models.world import WorldSetting
        import json as _json

        proj = (await self.db.execute(select(Project).where(Project.id == self.project_id))).scalar_one_or_none()
        parts = []
        # 核心世界观
        if proj:
            core = []
            if proj.world_time_period: core.append(f"时间背景：{proj.world_time_period}")
            if proj.world_location: core.append(f"地理位置：{proj.world_location}")
            if proj.world_atmosphere: core.append(f"氛围基调：{proj.world_atmosphere}")
            if proj.world_rules: core.append(f"世界规则：{proj.world_rules}")
            if core:
                parts.append("【核心世界观】\n" + "\n".join(core))

        # 详细设定条目
        worlds = (await self.db.execute(
            select(WorldSetting).where(WorldSetting.project_id == self.project_id)
        )).scalars().all()
        if worlds:
            detail = "\n".join([f"- {w.name}({w.category or '其他'})：{(w.content or '')[:150]}" for w in worlds[:15]])
            parts.append("【详细设定】\n" + detail)

        return {"world_setting": "\n".join(parts) if parts else "暂无世界设定"}

    async def _get_core_context(self, chapter: Chapter, project: Project) -> dict:
        """P0-核心信息"""
        # 本章大纲
        chapter_outline = ""
        expansion_plan = ""
        # 1对多模式：优先从 expansion_plan 构建结构化大纲
        if chapter.expansion_plan and isinstance(chapter.expansion_plan, dict):
            plan = chapter.expansion_plan
            parts = []
            if plan.get("plot_summary"):
                parts.append(f"剧情摘要：{plan['plot_summary']}")
            if plan.get("key_events"):
                parts.append("关键事件：\n" + "\n".join(f"- {e}" for e in plan["key_events"]))
            if plan.get("character_focus"):
                parts.append(f"角色焦点：{', '.join(plan['character_focus'])}")
            if plan.get("emotional_tone") or plan.get("emotional_arc"):
                parts.append(f"情感基调：{plan.get('emotional_arc') or plan.get('emotional_tone', '')}")
            if plan.get("narrative_goal"):
                parts.append(f"叙事目标：{plan['narrative_goal']}")
            if plan.get("conflict_type"):
                parts.append(f"冲突类型：{plan['conflict_type']}")
            if plan.get("scenes"):
                parts.append("场景：\n" + "\n".join(f"- {s}" for s in plan["scenes"]))
            # 富字段注入（爽点/钩子/情绪弧/场景锚点/微意图——让正文写作有明确发力点）
            if plan.get("rhythm_tag"):
                parts.append(f"节奏标记：{plan['rhythm_tag']}")
            if plan.get("hook"):
                parts.append(f"结尾钩子（写到此处停住）：{plan['hook']}")
            if plan.get("scene_anchor"):
                parts.append(f"场景锚点：{plan['scene_anchor']}")
            if plan.get("emotional_arc") and plan.get("emotional_arc") != plan.get("emotional_tone"):
                parts.append(f"情绪弧线：{plan['emotional_arc']}")
            if plan.get("shuang_design"):
                sd = plan["shuang_design"]
                if isinstance(sd, dict):
                    sd_parts = []
                    if sd.get("info_asymmetry"): sd_parts.append(f"信息差：{sd['info_asymmetry']}")
                    if sd.get("shock_level"): sd_parts.append(f"震惊层级：{sd['shock_level']}")
                    if sd.get("spectator_layers"): sd_parts.append("围观反应：" + "；".join(sd['spectator_layers']) if isinstance(sd['spectator_layers'], list) else str(sd['spectator_layers']))
                    if sd.get("emotional_rhythm"): sd_parts.append(f"情绪拉扯：{sd['emotional_rhythm']}")
                    if sd.get("protagonist_style"): sd_parts.append(f"主角逼格：{sd['protagonist_style']}")
                    if sd_parts:
                        parts.append("爽点设计：\n" + "\n".join(f"  - {p}" for p in sd_parts))
            if plan.get("character_intents"):
                ci = plan["character_intents"]
                if isinstance(ci, list):
                    intent_lines = []
                    for it in ci:
                        if isinstance(it, dict):
                            line = f"  - {it.get('character','?')}：本章目标「{it.get('this_chapter_goal','')}」，此刻想要「{it.get('immediate_want','')}」"
                            intent_lines.append(line)
                    if intent_lines:
                        parts.append("角色微意图：\n" + "\n".join(intent_lines))
            chapter_outline = "\n".join(parts) if parts else ""
            expansion_plan = chapter_outline
        elif chapter.expansion_plan:
            chapter_outline = str(chapter.expansion_plan)
            expansion_plan = chapter_outline
        # 1对多模式：注入所属卷（大纲）的内容，让正文写作有全局视野
        volume_outline = ""
        if chapter.outline_id:
            vol = (await self.db.execute(
                select(Outline).where(Outline.id == chapter.outline_id)
            )).scalar_one_or_none()
            if vol:
                vol_parts = [f"第{vol.chapter_number}卷《{vol.title or ''}》"]
                if vol.summary: vol_parts.append(f"本卷概览：{vol.summary}")
                if vol.goal: vol_parts.append(f"本卷目标：{vol.goal}")
                if vol.emotion: vol_parts.append(f"本卷基调：{vol.emotion}")
                volume_outline = "\n".join(vol_parts)
        # 1对1模式：从大纲表取（按 outline_id 或 chapter_number）
        if not chapter_outline:
            outline = None
            if chapter.outline_id:
                outline = (await self.db.execute(
                    select(Outline).where(Outline.id == chapter.outline_id)
                )).scalar_one_or_none()
            if not outline:
                outline = (await self.db.execute(
                    select(Outline).where(
                        Outline.project_id == self.project_id,
                        Outline.chapter_number == chapter.chapter_number,
                    ).order_by(Outline.id.desc())
                )).scalars().first()
            if outline:
                chapter_outline = outline.structure if outline.structure else {
                    "title": outline.title,
                    "summary": outline.summary,
                    "scenes": outline.scenes,
                    "characters": outline.characters,
                    "key_points": outline.key_points,
                    "emotion": outline.emotion,
                    "goal": outline.goal,
                }
                if isinstance(chapter_outline, dict):
                    import json
                    chapter_outline = json.dumps(chapter_outline, ensure_ascii=False, indent=2)

        # 最近 N 章大纲摘要
        result = await self.db.execute(
            select(Outline)
            .where(
                Outline.project_id == self.project_id,
                Outline.chapter_number < chapter.chapter_number,
            )
            .order_by(desc(Outline.chapter_number))
            .limit(settings.CHAPTER_CONTEXT_CHAPTERS)
        )
        recent_outlines = list(result.scalars().all())
        outlines_summary = "\n".join([
            f"第{o.chapter_number}章 {o.title}: {o.summary}" for o in reversed(recent_outlines)
        ])

        # 卷摘要前置注入（方案 A：在大纲摘要前插入卷级摘要，保障长期连贯性）
        try:
            vol_summaries = (await self.db.execute(
                select(StoryMemory).where(
                    StoryMemory.project_id == self.project_id,
                    StoryMemory.memory_type == "volume_summary",
                    StoryMemory.chapter_number < chapter.chapter_number,
                ).order_by(StoryMemory.chapter_number)
            )).scalars().all()
            if vol_summaries:
                vol_parts = []
                for vs in vol_summaries:
                    title = vs.title or f"第{vs.chapter_number}章前卷摘要"
                    vol_parts.append(f"【{title}】{vs.content}")
                # 全书主线脉络压缩（3+ 卷时）
                if len(vol_parts) >= 3:
                    recent_arcs = " → ".join(
                        vs.content[:50] + "…" for vs in vol_summaries[-5:]
                    )
                    vol_parts.append(f"【全书主线脉络】{recent_arcs}")
                outlines_summary = "\n\n".join(vol_parts) + "\n\n" + outlines_summary
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[context] 卷摘要注入失败（不影响生成）: {e}")

        # 上一章末尾
        result = await self.db.execute(
            select(Chapter).where(
                Chapter.project_id == self.project_id,
                Chapter.chapter_number == chapter.chapter_number - 1,
                Chapter.status == "completed",
            ).order_by(Chapter.id.desc())
        )
        prev_chapter = result.scalars().first()
        continuation_point = ""
        prev_summary = ""
        prev_chapter_content = ""
        if prev_chapter and prev_chapter.content:
            words = settings.CHAPTER_CONTEXT_WORDS
            continuation_point = prev_chapter.content[-words:] if len(prev_chapter.content) > words else prev_chapter.content
            prev_summary = prev_chapter.summary or ""
            # 前一章正文（截取最后 3000 字供模板使用）
            prev_chapter_content = prev_chapter.content[-3000:] if len(prev_chapter.content) > 3000 else prev_chapter.content

        # 最近几章上下文（最近 3 章末尾各 500 字拼接）
        result = await self.db.execute(
            select(Chapter)
            .where(
                Chapter.project_id == self.project_id,
                Chapter.chapter_number < chapter.chapter_number,
                Chapter.status == "completed",
            )
            .order_by(desc(Chapter.chapter_number))
            .limit(3)
        )
        recent_chapters = list(result.scalars().all())
        recent_chapters_context = "\n---\n".join([
            f"【第{c.chapter_number}章 末尾】\n{c.content[-500:]}" for c in recent_chapters if c.content
        ]) if recent_chapters else ""

        # ===== 连贯性增强：上一章剧情分析 + 角色当前状态 + 故事进度 =====
        prev_analysis_summary = ""
        character_current_states = ""
        story_progress = ""
        pending_foreshadows = ""
        recent_expansion_plans = ""  # 已写章节的规划摘要链（让 AI 回顾之前每章的剧情规划）
        quality_trends_detail = ""  # 质量分项趋势（pacing/engagement/coherence）
        try:
            # 前 2 章的剧情分析（形成连贯衔接，不只是上一章）
            if prev_chapter:
                prev_analyses = (await self.db.execute(
                    select(PlotAnalysis).where(
                        PlotAnalysis.project_id == self.project_id,
                        PlotAnalysis.chapter_number < chapter.chapter_number,
                    ).order_by(desc(PlotAnalysis.chapter_number)).limit(2)
                )).scalars().all()
                if prev_analyses:
                    pa_parts = []
                    for pa in reversed(prev_analyses):  # 按章节正序
                        parts_pa = []
                        parts_pa.append(f"第{pa.chapter_number}章")
                        ec = pa.emotional_curve if isinstance(pa.emotional_curve, dict) else {}
                        if ec.get('end'):
                            parts_pa.append(f"情感结尾：{ec['end']}")
                        if pa.plot_stage:
                            parts_pa.append(f"剧情阶段：{pa.plot_stage}")
                        # 关键情节点
                        if pa.key_plot_points:
                            kps = [p if isinstance(p, str) else p.get('event', p.get('description', '')) for p in (pa.key_plot_points or [])]
                            parts_pa.append("关键转折：" + "；".join(kps[:3]))
                        # 伏笔动态
                        if pa.foreshadows:
                            fs = [f"{f.get('type','')}{f.get('title','')}" for f in (pa.foreshadows or []) if isinstance(f, dict)]
                            parts_pa.append("伏笔动态：" + "、".join(fs[:3]))
                        # 未解决的冲突
                        if pa.conflicts:
                            cfs = [c.get('description', c.get('type', '')) if isinstance(c, dict) else str(c) for c in (pa.conflicts or [])]
                            parts_pa.append("未决冲突：" + "；".join(cfs[:2]))
                        pa_parts.append("｜".join(parts_pa))
                    # 最近一章的改进建议
                    latest = prev_analyses[0]
                    if latest.suggestions:
                        sugs = [s if isinstance(s, str) else s.get('suggestion', '') for s in (latest.suggestions or [])]
                        pa_parts.append("上章改进建议（本章注意）：" + "；".join(sugs[:2]))
                    prev_analysis_summary = "\n".join(p for p in pa_parts if p.strip())

            # 角色当前状态（优先用该章节前的历史快照，避免未来信息泄露）
            _chars = (await self.db.execute(
                select(Character).where(Character.project_id == self.project_id)
            )).scalars().all()
            from app.api.routes.projects_pkg.characters import get_character_state_at_chapter
            char_states_parts = []
            for char in _chars[:8]:  # 主要角色
                # 尝试获取章节前的历史快照
                snapshot = await get_character_state_at_chapter(self.db, self.project_id, char.id, chapter.chapter_number)
                state = snapshot if snapshot else {}
                state_parts = [char.name]
                mental = state.get('mental_state', char.mental_state)
                status = state.get('status', char.status)
                stage = state.get('main_career_stage_desc', '') or str(state.get('main_career_stage', getattr(char, 'main_career_stage', '') or ''))
                if mental:
                    state_parts.append(f"心理：{str(mental)[:40]}")
                if status and str(status) != "alive":
                    state_parts.append(f"状态：{status}")
                if stage and str(stage) not in ('0', '', 'None'):
                    state_parts.append(f"境界：{stage}")
                if len(state_parts) > 1:
                    char_states_parts.append("（" + "，".join(state_parts[1:]) + "）")
            if char_states_parts:
                character_current_states = "；".join(char_states_parts[:6])

            # 故事进度概览
            total_chapters_written = await self.db.scalar(
                select(func.count(Chapter.id)).where(
                    Chapter.project_id == self.project_id,
                    Chapter.status == "completed",
                )
            )
            total_words = await self.db.scalar(
                select(func.sum(Chapter.word_count)).where(Chapter.project_id == self.project_id)
            )
            story_progress = f"已完成 {total_chapters_written or 0} 章，累计 {total_words or 0} 字"

            # 待回收/即将到期的伏笔提醒（直接注入，不依赖生成时 foreshadow_service）
            pending_fs = await self.foreshadow_service.get_pending_resolve_foreshadows(chapter.chapter_number, lookahead=5)
            overdue_fs = await self.foreshadow_service.get_overdue_foreshadows(chapter.chapter_number)
            fs_parts = []
            if overdue_fs:
                fs_parts.append("⚠️ 超期必须回收：" + "、".join(f"《{f.title}》({f.content[:20]}…)" for f in overdue_fs[:8]))
            if pending_fs:
                fs_parts.append("近期应回收：" + "、".join(f"《{f.title}》({f.content[:20]}…)" for f in pending_fs[:8]))
            if fs_parts:
                pending_foreshadows = "\n".join(fs_parts)

            # 已写章节的 expansion_plan 规划摘要链（让 AI 回顾之前每章规划了什么剧情）
            recent_written = (await self.db.execute(
                select(Chapter).where(
                    Chapter.project_id == self.project_id,
                    Chapter.chapter_number < chapter.chapter_number,
                    Chapter.status == "completed",
                ).order_by(desc(Chapter.chapter_number)).limit(10)
            )).scalars().all()
            plan_parts = []
            for rc in reversed(recent_written):  # 按章节正序
                if rc.expansion_plan and isinstance(rc.expansion_plan, dict):
                    ep = rc.expansion_plan
                    summary = ep.get("plot_summary", rc.summary or "")[:100]
                    plan_parts.append(f"第{rc.chapter_number}章：{summary}")
                elif rc.summary:
                    plan_parts.append(f"第{rc.chapter_number}章：{rc.summary[:100]}")
            if plan_parts:
                recent_expansion_plans = "\n".join(plan_parts)

            # 质量分项趋势（最近5章 8维度评分）
            recent_analyses = (await self.db.execute(
                select(PlotAnalysis).where(
                    PlotAnalysis.project_id == self.project_id,
                    PlotAnalysis.chapter_number < chapter.chapter_number,
                ).order_by(desc(PlotAnalysis.chapter_number)).limit(5)
            )).scalars().all()
            if recent_analyses:
                trend_parts = []
                for ra in reversed(recent_analyses):
                    qs = ra.quality_scores or {}
                    overall = qs.get("overall", "-")
                    pacing = qs.get("pacing", "-")
                    engagement = qs.get("engagement", "-")
                    coherence = qs.get("coherence", "-")
                    writing = qs.get("writing_quality", "-")
                    char_depth = qs.get("character_depth", "-")
                    dialogue = qs.get("dialogue_quality", "-")
                    world = qs.get("world_consistency", "-")
                    logic = qs.get("plot_logic", "-")
                    trend_parts.append(
                        f"第{ra.chapter_number}章：综合{overall} 节奏{pacing} 吸引力{engagement} "
                        f"连贯性{coherence} 文笔{writing} 角色{char_depth} "
                        f"对话{dialogue} 设定{world} 逻辑{logic}"
                    )
                quality_trends_detail = "\n".join(trend_parts)
                # 追加最近一章的改进建议
                latest_suggestions = recent_analyses[0].suggestions or []
                if latest_suggestions:
                    sugs = [s if isinstance(s, str) else s.get("suggestion", "") for s in latest_suggestions[:2]]
                    quality_trends_detail += "\n最近改进建议：" + "；".join(sugs)
                # 追加最近一章的一致性问题（如果有）
                latest_analysis = recent_analyses[0]
                if hasattr(latest_analysis, 'consistency_issues') and latest_analysis.consistency_issues:
                    issues = latest_analysis.consistency_issues
                    if isinstance(issues, list) and issues:
                        quality_trends_detail += "\n⚠️ 上章一致性问题：" + "；".join(str(i) for i in issues[:3])
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[context] 连贯性增强信息加载失败（不影响生成）: {e}")

        # 字数要求
        word_count_requirement = f"目标{settings.CHAPTER_DEFAULT_WORDS}字，不少于{settings.CHAPTER_MIN_WORDS}字，不超过{settings.CHAPTER_MAX_WORDS}字"
        target_word_count = word_count_requirement  # JSON 模板用这个变量名

        # 组织信息（组织列表已在 world_context 中提供，此处省略）
        chapter_careers = ""
        # ===== 场景锚点 + 角色微意图 =====
        scene_anchor = ""
        character_intents = ""
        # 1-to-many: 从 expansion_plan 提取
        if chapter.expansion_plan and isinstance(chapter.expansion_plan, dict):
            plan = chapter.expansion_plan
            sa = plan.get("scene_anchor", "")
            if sa:
                scene_anchor = str(sa)
            ci = plan.get("character_intents", [])
            if ci and isinstance(ci, list):
                lines = []
                for item in ci:
                    if isinstance(item, dict):
                        name = item.get("character", item.get("name", "?"))
                        goal = item.get("this_chapter_goal", "")
                        want = item.get("immediate_want", "")
                        lines.append(f"  {name}：本章目标={goal}；此刻想要={want}")
                    elif isinstance(item, str):
                        lines.append(f"  {item}")
                if lines:
                    character_intents = "本章角色微意图：\n" + "\n".join(lines)
        # 1-to-1: 从 outline.structure 提取
        if not scene_anchor or not character_intents:
            ol_struct = None
            if not chapter.outline_id:
                ol = (await self.db.execute(
                    select(Outline).where(
                        Outline.project_id == self.project_id,
                        Outline.chapter_number == chapter.chapter_number,
                    ).order_by(Outline.id.desc())
                )).scalars().first()
            else:
                ol = (await self.db.execute(
                    select(Outline).where(Outline.id == chapter.outline_id)
                )).scalar_one_or_none()
            if ol and ol.structure and isinstance(ol.structure, dict):
                ol_struct = ol.structure
            if ol_struct:
                if not scene_anchor:
                    sa = ol_struct.get("scene_anchor", "")
                    if sa:
                        scene_anchor = str(sa)
                if not character_intents:
                    ci = ol_struct.get("character_intents", [])
                    if ci and isinstance(ci, list):
                        lines = []
                        for item in ci:
                            if isinstance(item, dict):
                                name = item.get("character", item.get("name", "?"))
                                goal = item.get("this_chapter_goal", "")
                                want = item.get("immediate_want", "")
                                lines.append(f"  {name}：本章目标={goal}；此刻想要={want}")
                            elif isinstance(item, str):
                                lines.append(f"  {item}")
                        if lines:
                            character_intents = "本章角色微意图：\n" + "\n".join(lines)

        return {
            # 原有 key（builtin 模板使用）
            "chapter_outline": chapter_outline,
            "recent_outlines": outlines_summary,
            "continuation_point": continuation_point,
            "previous_summary": prev_summary,
            "word_count_requirement": word_count_requirement,
            "narrative_pov": project.narrative_pov or "第三人称",
            "expansion_plan": expansion_plan,
            # 新增 key（JSON 模板使用）
            "project_title": project.title or "",
            "chapter_number": str(chapter.chapter_number),
            "chapter_title": chapter.title or "",
            "genre": project.genre or "",
            "target_word_count": target_word_count,
            "narrative_perspective": project.narrative_pov or "第三人称",
            "chapter_careers": chapter_careers,
            "previous_chapter_content": prev_chapter_content,
            "previous_chapter_summary": prev_summary,
            "recent_chapters_context": recent_chapters_context,
            # ===== 连贯性增强（让第二章能衔接第一章）=====
            "previous_analysis": prev_analysis_summary,
            "character_current_states": character_current_states,
            "story_progress": story_progress,
            "pending_foreshadows": pending_foreshadows,
            "recent_expansion_plans": recent_expansion_plans,
            "quality_trends_detail": quality_trends_detail,
            # ===== 卷级上下文（1对多模式：所属卷的大纲，让正文写作有全局视野）=====
            "volume_outline": volume_outline or "",
            # ===== 场景锚点 + 角色微意图 =====
            "scene_anchor": scene_anchor or "（本章未提供场景锚点）",
            "character_intents": character_intents or "（本章未提供角色微意图）",
        }

    async def _get_important_context(self, chapter: Chapter) -> dict:
        """P1-重要信息：角色完整信息 + 关系网络 + 组织归属"""
        from app.models.character import CharacterRelation
        from app.models.organization import Organization
        import json

        result = await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )
        characters = list(result.scalars().all())

        # 预加载关系网（一次查询，避免 N+1），限制数量防止膨胀
        rels = (await self.db.execute(
            select(CharacterRelation).where(CharacterRelation.project_id == self.project_id).limit(30)
        )).scalars().all()
        # name → 角色名映射，构造 {char_id: ["A--师徒-->B", ...]}
        id_to_name = {c.id: c.name for c in characters}
        rel_map = {}
        for r in rels:
            fname = id_to_name.get(r.from_character_id, "?")
            tname = id_to_name.get(r.to_character_id, "?")
            rel_map.setdefault(r.from_character_id, []).append(
                f"{fname}与{tname}是{r.relation_type}关系(亲密度{r.intimacy})"
            )

        # 预加载组织
        orgs = (await self.db.execute(
            select(Organization).where(Organization.project_id == self.project_id)
        )).scalars().all()
        org_map = {o.id: o for o in orgs}

        # 智能筛选：本章涉及的角色（从大纲/扩展计划提取）+ 主角 + 反派，其余只留名字
        # 目的：防止几百章后角色膨胀导致上下文爆炸
        def _extract_char_names(raw):
            """从大纲 characters 字段提取角色名（兼容字符串/对象数组）"""
            names = set()
            if not raw:
                return names
            if isinstance(raw, str):
                names.add(raw)
            elif isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str):
                        names.add(item)
                    elif isinstance(item, dict):
                        n = item.get("name") or item.get("character_name")
                        if n:
                            names.add(str(n))
            return names

        chapter_character_names = set()
        # 从 expansion_plan 提取角色焦点
        if chapter.expansion_plan and isinstance(chapter.expansion_plan, dict):
            chapter_character_names.update(_extract_char_names(chapter.expansion_plan.get("character_focus")))
        # 从本章大纲提取角色
        if chapter.outline_id:
            ol = (await self.db.execute(select(Outline).where(Outline.id == chapter.outline_id))).scalar_one_or_none()
            if ol and ol.characters:
                chapter_character_names.update(_extract_char_names(ol.characters))
        # 也从 chapter_number 匹配的大纲提取（1对1模式 outline_id 可能为空）
        if not chapter_character_names:
            ol = (await self.db.execute(
                select(Outline).where(Outline.project_id == self.project_id, Outline.chapter_number == chapter.chapter_number)
                .order_by(Outline.id.desc())
            )).scalars().first()
            if ol and ol.characters:
                chapter_character_names.update(_extract_char_names(ol.characters))

        # 分层：核心角色（本章涉及+主角+反派）完整输出，其他角色仅名字+定位
        # 如果本章角色名和角色表对不上（AI 生成的名字不一致），退化为前N个完整
        MAX_FULL_CHARS = 12
        core_chars = []
        minor_chars = []
        for c in characters:
            if c.name in chapter_character_names or c.role in ("主角", "反派"):
                core_chars.append(c)
            else:
                minor_chars.append(c)
        # 兜底：如果核心角色为空（名字对不上），取前 6 个角色完整展示
        if not core_chars and characters:
            core_chars = characters[:6]
            minor_chars = characters[6:]
        # 如果核心角色太多，截断
        if len(core_chars) > MAX_FULL_CHARS:
            minor_chars = core_chars[MAX_FULL_CHARS:] + minor_chars
            core_chars = core_chars[:MAX_FULL_CHARS]

        chars_info_parts = []
        from app.api.routes.projects_pkg.characters import get_character_state_at_chapter
        # 核心角色：完整信息（对于有变化日志的角色，使用章节前的历史快照）
        for c in core_chars:
            snapshot = await get_character_state_at_chapter(self.db, self.project_id, c.id, chapter.chapter_number)
            s = snapshot if snapshot else {}
            _st = s.get('status', c.status)
            _ms = s.get('mental_state', c.mental_state)
            _ap = s.get('appearance', c.appearance)
            _pe = s.get('personality', c.personality)
            _bg = s.get('background', c.background)
            _ab = s.get('ability', c.ability)
            _oi = s.get('organization_id', c.organization_id)
            _id = s.get('identity', c.identity)
            _wk = s.get('weakness', c.weakness)
            _sg = s.get('story_goal', c.story_goal)
            _mo = s.get('motivation', c.motivation)
            _ge = s.get('growth_experience', c.growth_experience)
            _at = s.get('arc_type', c.arc_type)
            _cc = s.get('character_change', c.character_change)
            _cs = s.get('main_career_stage_desc', c.main_career_stage_desc)
            parts = [f"【{c.name}】{c.role}，{c.gender}，{c.age}岁"]
            if _id:
                parts.append(f"  身份：{str(_id)[:100]}")
            if _st and str(_st) != "alive":
                parts.append(f"  状态：{_st}")
            if _ms:
                parts.append(f"  当前心理：{str(_ms)[:60]}")
            if _ap:
                parts.append(f"  外貌：{str(_ap)[:120]}")
            if _pe:
                parts.append(f"  性格：{str(_pe)[:120]}")
            if _bg:
                parts.append(f"  背景：{str(_bg)[:120]}")
            if _ab:
                parts.append(f"  能力：{str(_ab)[:120]}")
            if _wk:
                parts.append(f"  弱点：{str(_wk)[:100]}")
            if _sg:
                parts.append(f"  目标：{str(_sg)[:100]}")
            if _mo:
                parts.append(f"  动机：{str(_mo)[:100]}")
            if _ge:
                parts.append(f"  成长经历：{str(_ge)[:120]}")
            if _at:
                parts.append(f"  人物弧线：{_at}")
            if _cc:
                parts.append(f"  变化轨迹：{str(_cc)[:120]}")
            if _cs:
                parts.append(f"  境界：{str(_cs)[:60]}")
            # 组织归属
            org_id = _oi or c.organization_id
            if org_id and org_id in org_map:
                org = org_map[org_id]
                parts.append(f"  所属组织：{org.name}({org.org_type or ''})")
            # 关系网络
            rels_text = rel_map.get(c.id)
            if rels_text:
                parts.append(f"  关系网络：{'；'.join(rels_text[:5])}")
            elif c.relationships:
                parts.append(f"  关系：{str(c.relationships)[:150]}")
            chars_info_parts.append("\n".join(parts))

        # 次要角色：仅名字+定位（一行一个，节省上下文）
        if minor_chars:
            minor_names = [f"{c.name}（{c.role or '配角'}）" for c in minor_chars[:20]]  # 最多列20个
            chars_info_parts.append("其他角色：" + "、".join(minor_names))

        characters_info = "\n\n".join(chars_info_parts) if chars_info_parts else "暂无角色信息"

        # 写作风格
        proj = (await self.db.execute(select(Project).where(Project.id == self.project_id))).scalar_one_or_none()
        writing_style = ""
        style_custom_prompt = ""
        style_traits = ""
        style_reference_text = ""
        author_name = ""
        style_enable_traits = True
        style_enable_custom = True
        style_enable_dimensions = True
        if proj and proj.writing_style:
            ws = proj.writing_style
            # 提取用户自定义提示词（高级），单独注入让 AI 明确遵循
            style_custom_prompt = (ws.get("custom_prompt") or "").strip()
            # 三个区块开关（跟随 apply 快照；兼容旧 disable_dimensions）
            style_enable_traits = ws.get("enable_traits") if ws.get("enable_traits") is not None else True
            style_enable_custom = ws.get("enable_custom") if ws.get("enable_custom") is not None else True
            if ws.get("enable_dimensions") is not None:
                style_enable_dimensions = bool(ws.get("enable_dimensions"))
            else:
                style_enable_dimensions = not bool(ws.get("disable_dimensions"))
            # 作家文风模仿：若记录了来源 style_id，则读取「最新」的特征/范文/作家名，
            # 这样用户重新提炼后无需再次"设为项目默认"即可生效。
            latest_traits = None
            latest_ref = None
            latest_author = None
            _sid = ws.get("style_id")
            if isinstance(_sid, int):
                from app.models.writing_style import WritingStyle as _WS
                ws_row = (await db.execute(select(_WS).where(_WS.id == _sid))).scalar_one_or_none()
                if ws_row:
                    latest_traits = ws_row.style_traits or {}
                    latest_ref = (ws_row.reference_text or "").strip()
                    latest_author = (ws_row.author_name or "").strip()
            # 覆盖快照：优先用最新值，没有则回退快照
            _traits = latest_traits if latest_traits is not None else ws.get("style_traits")
            if isinstance(_traits, dict) and _traits:
                style_traits = json.dumps(_traits, ensure_ascii=False)
            elif isinstance(_traits, str) and _traits.strip():
                style_traits = _traits.strip()
            author_name = (latest_author if latest_author is not None else (ws.get("author_name") or "")).strip()
            style_reference_text = (latest_ref if latest_ref is not None else (ws.get("reference_text") or "")).strip()
            writing_style = json.dumps(ws, ensure_ascii=False)

        return {
            "characters_info": characters_info,
            "writing_style": writing_style or "默认网文风格，节奏明快",
            "style_custom_prompt": style_custom_prompt,
            "style_traits": style_traits,
            "style_reference_text": style_reference_text,
            "author_name": author_name,
            "style_enable_traits": style_enable_traits,
            "style_enable_custom": style_enable_custom,
            "style_enable_dimensions": style_enable_dimensions,
        }

    async def _get_reference_context(self, chapter: Chapter) -> dict:
        """P2-参考信息：记忆检索 + 上一章关键事件 + 伏笔提醒"""
        # 记忆：优先取与本章相关角色/近期章节的记忆（对标原项目语义检索，简化版）
        # 按 importance 排序，但优先近期章节（chapter_number 接近）
        result = await self.db.execute(
            select(StoryMemory)
            .where(
                StoryMemory.project_id == self.project_id,
                StoryMemory.importance >= settings.MEMORY_SIMILARITY_THRESHOLD,
            )
            .order_by(desc(StoryMemory.importance))
            .limit(20)
        )
        memories = list(result.scalars().all())
        # 按类型分组，让 AI 更易理解
        mem_by_type = {}
        for m in memories:
            mem_by_type.setdefault(m.memory_type or "other", []).append(m.content)
        if mem_by_type:
            relevant_memories = "\n".join([
                f"[{t}] " + "；".join(items[:4])
                for t, items in mem_by_type.items()
            ])
        else:
            relevant_memories = "暂无相关记忆"

        # 上一章关键事件：从剧情分析提取（对标原项目 key_events）
        prev_key_events = ""
        prev_analysis = (await self.db.execute(
            select(PlotAnalysis).where(
                PlotAnalysis.project_id == self.project_id,
                PlotAnalysis.chapter_number == chapter.chapter_number - 1,
            )
        )).scalar_one_or_none()
        if prev_analysis:
            ev_parts = []
            # 剧情分析里的关键情节点
            if prev_analysis.key_plot_points:
                for kp in (prev_analysis.key_plot_points if isinstance(prev_analysis.key_plot_points, list) else [])[:5]:
                    if isinstance(kp, dict):
                        ev_parts.append(f"- {kp.get('event', kp.get('title', str(kp)[:60]))}")
                    else:
                        ev_parts.append(f"- {str(kp)[:60]}")
            # 冲突进展
            if prev_analysis.conflicts:
                for cf in (prev_analysis.conflicts if isinstance(prev_analysis.conflicts, list) else [])[:3]:
                    if isinstance(cf, dict) and cf.get("resolution_progress"):
                        ev_parts.append(f"- 冲突: {cf.get('description', '')[:50]} → {cf['resolution_progress']}")
            # 角色状态变化
            if prev_analysis.character_states:
                for cs in (prev_analysis.character_states if isinstance(prev_analysis.character_states, list) else [])[:3]:
                    if isinstance(cs, dict):
                        ev_parts.append(f"- {cs.get('character', '')}: {cs.get('state_after', cs.get('change', str(cs)[:40]))}")
            if ev_parts:
                prev_key_events = f"【上一章关键事件/角色变化】\n" + "\n".join(ev_parts)

        # 伏笔提醒（分层：必须回收/即将到期/其他）
        foreshadow_reminders = await self.foreshadow_service.get_foreshadow_reminders(
            chapter.chapter_number
        )

        return {
            "relevant_memories": relevant_memories,
            "foreshadow_reminders": foreshadow_reminders,
            "prev_key_events": prev_key_events or "暂无",
        }

    async def _get_quality_context(self, chapter: Chapter) -> dict:
        """P3-评分反馈"""
        result = await self.db.execute(
            select(PlotAnalysis)
            .where(
                PlotAnalysis.project_id == self.project_id,
                PlotAnalysis.chapter_number < chapter.chapter_number,
            )
            .order_by(desc(PlotAnalysis.chapter_number))
            .limit(settings.QUALITY_TREND_COUNT)
        )
        analyses = list(result.scalars().all())

        if analyses:
            lines = ["最近章节评分趋势："]
            for a in reversed(analyses):
                scores = a.quality_scores or {}
                overall = scores.get("overall", "N/A")
                lines.append(f"  第{a.chapter_number}章: 综合{overall}/10")
                if a.suggestions:
                    for s in a.suggestions[:2]:
                        lines.append(f"    建议: {s}")
            quality_trends = "\n".join(lines)
        else:
            quality_trends = "暂无评分数据"

        return {"quality_trends": quality_trends}