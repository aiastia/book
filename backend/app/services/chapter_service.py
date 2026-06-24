"""章节生成服务 - 核心逻辑链路"""
import json
import re
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.outline import Outline
from app.models.character import Character
from app.models.world import WorldSetting
from app.models.plot_analysis import PlotAnalysis
from app.models.story_memory import StoryMemory
from app.models.generation_history import GenerationHistory
from app.services.chapter_context_service import ChapterContextService
from app.services.foreshadow_service import ForeshadowService
from app.skills.engine import SkillEngine
from app.core.ai_client import AIClient
from app.core.config import settings


# 分析报告评分维度展示顺序（含番茄平台维度，自动支持任意维度）
_SCORE_ORDER = [
    ("overall", "整体质量"),
    ("pacing", "节奏把控"),
    ("engagement", "吸引力"),
    ("coherence", "连贯性"),
    ("writing_quality", "文笔质量"),
    ("character_depth", "角色塑造"),
    ("dialogue_quality", "对话质量"),
    ("world_consistency", "世界观一致性"),
    ("plot_logic", "剧情逻辑"),
    ("attraction", "番茄吸量力"),
    ("retention", "番茄留存力"),
    ("bookmark_ratio", "番茄追更比潜力"),
]


def generate_analysis_summary(analysis_data: dict) -> str:
    """根据分析结果生成标准格式的分析报告文本（对标 MuMu generate_analysis_summary）。

    输出格式（带【整体评分】【剧情阶段】等标题），存入 PlotAnalysis.analysis_report，
    前端用正则解析该文本渲染评分卡片 + 整段展示为「分析摘要」。
    """
    try:
        lines = ["=== 章节分析报告 ===\n"]

        # ===== 整体评分（动态遍历，支持任意维度数） =====
        scores = analysis_data.get("quality_scores") or analysis_data.get("scores") or {}
        lines.append("【整体评分】")
        shown = False
        for key, label in _SCORE_ORDER:
            val = scores.get(key)
            if val is not None and val != "":
                try:
                    lines.append(f"  {label}: {float(val):.1f}/10")
                    shown = True
                except (ValueError, TypeError):
                    pass
        if not shown:
            lines.append(f"  整体质量: {scores.get('overall', 'N/A')}/10")

        # 评分理由（AI 必填的逐维度说明）：分号转成换行，每维度独占一行
        justification = scores.get("score_justification") or scores.get("justification")
        if justification:
            # 兜底：AI 可能误用英文 key（如 pacing/attraction）作为维度标题，
            # 这里统一替换成中文名，确保前端展示一致。
            for key, label in _SCORE_ORDER:
                justification = re.sub(
                    rf'\b{re.escape(key)}\b(?=\s*[:：])',
                    label,
                    justification,
                )
            # 中英文分号转换行，让每维度理由独占一行更易读
            formatted = justification.replace("；", "\n  ").replace(";", "\n  ")
            lines.append(f"  评分理由: \n  {formatted.strip()}")
        lines.append("")

        # ===== 剧情阶段 =====
        lines.append(f"【剧情阶段】{analysis_data.get('plot_stage', '未知')}\n")

        # ===== 钩子分析（兼容 dict / list 格式） =====
        hooks_raw = analysis_data.get("hooks", [])
        hook_items = []
        if isinstance(hooks_raw, list):
            hook_items = hooks_raw
        elif isinstance(hooks_raw, dict):
            hook_items = [
                {"type": k, "content": v, "strength": 8}
                for k, v in hooks_raw.items() if v
            ]
        if hook_items:
            lines.append(f"【钩子分析】共{len(hook_items)}个")
            for h in hook_items[:3]:
                htype = h.get("type", "钩子") if isinstance(h, dict) else "钩子"
                hcontent = (h.get("content") or h.get("text") or "") if isinstance(h, dict) else str(h)
                hstrength = h.get("strength", 0) if isinstance(h, dict) else 0
                lines.append(f"  • [{htype}] {hcontent[:60]}... (强度:{hstrength})")
            lines.append("")

        # ===== 伏笔分析 =====
        foreshadows = analysis_data.get("foreshadows", [])
        if foreshadows:
            planted = sum(1 for f in foreshadows if isinstance(f, dict) and f.get("type") == "planted")
            resolved = sum(1 for f in foreshadows if isinstance(f, dict) and f.get("type") == "resolved")
            lines.append(f"【伏笔分析】埋下{planted}个, 回收{resolved}个\n")

        # ===== 冲突分析 =====
        conflicts = analysis_data.get("conflicts", [])
        conflict_types = analysis_data.get("conflict_types", [])
        if conflicts or conflict_types:
            lines.append("【冲突分析】")
            if conflict_types:
                lines.append(f"  类型: {', '.join(conflict_types)}")
            if conflicts and isinstance(conflicts[0], dict):
                c0 = conflicts[0]
                intensity = c0.get("intensity") or c0.get("level") or 0
                try:
                    intensity = int(float(intensity))
                except (ValueError, TypeError):
                    intensity = 0
                progress = c0.get("progress", "")
                lines.append(f"  强度: {intensity}/10")
                if progress:
                    lines.append(f"  进度: {progress}")
            lines.append("")

        # ===== 改进建议 =====
        suggestions = analysis_data.get("suggestions", [])
        if suggestions:
            lines.append("【改进建议】")
            for i, sug in enumerate(suggestions, 1):
                text = sug if isinstance(sug, str) else (
                    sug.get("suggestion") or sug.get("content") or str(sug)
                )
                lines.append(f"  {i}. {text}")

        return "\n".join(lines)
    except Exception as e:
        print(f"[generate_analysis_summary] 生成摘要失败: {e}", flush=True)
        return "分析摘要生成失败"


class ChapterService:
    def __init__(self, db: AsyncSession, project_id: int, user_id: int = None):
        self.db = db
        self.project_id = project_id
        self.user_id = user_id
        self.foreshadow_service = ForeshadowService(db, project_id)
        self.context_service = ChapterContextService(db, project_id, user_id)
        self.skill_engine = SkillEngine(db, user_id)

    async def _get_chapter_and_project(self, chapter_id: int) -> tuple[Chapter, Project]:
        """获取章节和项目，校验基本条件"""
        result = await self.db.execute(select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == self.project_id,
        ))
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise ValueError("章节不存在")

        result = await self.db.execute(select(Project).where(Project.id == self.project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError("项目不存在")

        return chapter, project

    async def _validate_generation(self, chapter: Chapter):
        """预验证"""
        if chapter.content and len(chapter.content.strip()) > 0:
            raise ValueError("章节已有内容，请清空后重新生成")

        # 检查前置章节
        if chapter.chapter_number > 1:
            result = await self.db.execute(select(Chapter).where(
                Chapter.project_id == self.project_id,
                Chapter.chapter_number == chapter.chapter_number - 1,
            ).order_by(Chapter.id.desc()))
            prev = result.scalars().first()
            if prev and prev.status not in ("completed", "reviewed"):
                raise ValueError(f"前置章节（第{prev.chapter_number}章）尚未完成")

    def _determine_generation_mode(self, chapter: Chapter) -> tuple[str, str]:
        """确定生成模式和 Skill 名称

        使用 JSON 导入的技能名（chapter_generation_*），比 builtin 版本提示词更精细。
        第1章用基础版，第2章及以后用 _next 版本（含前文衔接变量）。
        """
        if chapter.chapter_number and chapter.chapter_number > 1:
            # 第2章及以后：使用 _next 变体
            if chapter.expansion_plan:
                return "one_to_many", "chapter_generation_one_to_many_next"
            return "one_to_one", "chapter_generation_one_to_one_next"
        # 第1章
        if chapter.expansion_plan:
            return "one_to_many", "chapter_generation_one_to_many"
        return "one_to_one", "chapter_generation_one_to_one"

    async def _get_ai_client(self, project: Project) -> AIClient:
        """获取 AI 客户端（用户配置优先）"""
        from app.models.ai_model import AIModelConfig
        if self.user_id:
            result = await self.db.execute(
                select(AIModelConfig).where(
                    AIModelConfig.user_id == self.user_id,
                    AIModelConfig.is_default == True,
                )
            )
            config = result.scalar_one_or_none()
            if config:
                return AIClient(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    model=config.model,
                    provider=config.provider or config.backend_type or "openai",
                    embedding_model=config.embedding_model or "",
                )
        return AIClient()

    async def _run_planner_and_fetch(
        self, chapter: Chapter, project: Project,
        base_context: dict, ai_client: AIClient,
    ) -> str:
        """Phase 1+2: Planner 判断需求 → Fetcher 按需查询 → 返回 <data> 文本块。"""
        import json as _json
        from app.services.memory_vector_service import MemoryVectorService

        # === Phase 1: Planner ===
        planner_context = {
            "chapter_number": str(chapter.chapter_number),
            "chapter_title": chapter.title or "",
            "target_word_count": str(base_context.get("target_word_count", 3000)),
            "user_prompt": "",
        }
        plan_result = await self.skill_engine.execute_skill(
            "chapter_planner", ai_client, planner_context,
        )
        plan_json = plan_result.get("json") or {}
        needs = plan_json.get("need", [])
        if not isinstance(needs, list) or not needs:
            raise RuntimeError("Planner 返回空的 need 列表")

        # === Phase 2: Fetcher ===
        parts = []
        chapter_num = chapter.chapter_number
        # 预加载常用数据（避免重复查询）
        chars_cache = None
        outlines_cache = None

        for need in needs:
            need = need.strip()
            parts.append(f"<!-- {need} -->")
            try:
                if need.startswith("角色:"):
                    name = need[3:].strip()
                    if name == "all":
                        chars = await self._list_chapter_characters(chapter)
                        parts.append("<characters>")
                        for c in chars:
                            parts.append(
                                f"  [{c.name}] 定位:{c.role} 身份:{c.identity or ''} "
                                f"性格:{c.personality[:120]} 背景:{c.background[:120]} "
                                f"能力:{c.ability[:100]} 弱点:{c.weakness[:80]} "
                                f"目标:{c.story_goal[:80]} 说话风格:{c.speech_style[:80]} "
                                f"弧线:{c.arc_type or ''} 境界:{c.main_career_stage_desc or ''}"
                            )
                        parts.append("</characters>")
                    else:
                        info = await self._query_character(name)
                        parts.append(f"<character name=\"{name}\">{info}</character>")
                elif need.startswith("关系:"):
                    name = need[3:].strip()
                    info = await self._query_relations(name)
                    parts.append(f"<relations of=\"{name}\">{info}</relations>")
                elif need.startswith("前章:"):
                    n = int(need[3:].strip())
                    info = await self._query_chapter_summary(n)
                    parts.append(f"<chapter_summary ch=\"{n}\">{info}</chapter_summary>")
                elif need == "大纲":
                    ol = await self._get_outline_for_chapter(chapter_num)
                    if ol:
                        parts.append(f"<outline>{ol}</outline>")
                elif need.startswith("伏笔"):
                    filt = need[3:] if len(need) > 2 else "all"
                    ftext = await self._query_foreshadows_text(filt, chapter_num)
                    parts.append(f"<foreshadows>{ftext}</foreshadows>")
                elif need.startswith("组织:"):
                    name = need[3:].strip()
                    info = await self._query_organization(name)
                    parts.append(f"<organization name=\"{name}\">{info}</organization>")
                elif need.startswith("时间线"):
                    q = need[4:].strip() if len(need) > 4 else ""
                    info = await self._query_timeline(q, chapter_num)
                    parts.append(f"<timeline query=\"{q}\">{info}</timeline>")
                elif need == "世界观":
                    wtext = await self._get_world_settings_text()
                    if wtext:
                        parts.append(f"<world>{wtext}</world>")
                elif need == "回忆":
                    vs = MemoryVectorService(ai_client)
                    ol_text = ""
                    if chapter.outline_id:
                        from sqlalchemy import select as _s
                        ol = (await self.db.execute(
                            _s(Outline).where(Outline.id == chapter.outline_id)
                        )).scalar_one_or_none()
                        if ol:
                            ol_text = (ol.summary or ol.title or "")[:500]
                    recalled = await vs.build_context_for_generation(
                        user_id=self.user_id, project_id=self.project_id,
                        current_chapter=chapter_num,
                        chapter_outline=ol_text,
                        top_k=3,
                    )
                    if recalled:
                        parts.append(f"<memories>{recalled[:1500]}</memories>")
            except Exception as e:
                parts.append(f"(查询失败: {e})")

        return "\n\n".join(parts)

    async def _list_chapter_characters(self, chapter: Chapter) -> list:
        """获取本章涉及的角色列表。"""
        from app.models.outline import Outline
        names = set()
        # 从大纲取
        if chapter.outline_id:
            ol = (await self.db.execute(
                select(Outline).where(Outline.id == chapter.outline_id)
            )).scalar_one_or_none()
            if ol and ol.characters:
                for c in ol.characters:
                    if isinstance(c, str):
                        names.add(c)
                    elif isinstance(c, dict):
                        names.add(c.get("name", ""))
        if not names:
            # 回退：所有角色
            chars = (await self.db.execute(
                select(Character).where(Character.project_id == self.project_id)
            )).scalars().all()
            return chars[:8]
        chars = (await self.db.execute(
            select(Character).where(
                Character.project_id == self.project_id,
                Character.name.in_(list(names)),
            )
        )).scalars().all()
        return chars or []

    async def _query_character(self, name: str) -> str:
        from app.services.chapter_tools import _query_character
        return await _query_character(self.db, self.project_id, name)

    async def _query_relations(self, name: str) -> str:
        from app.services.chapter_tools import _query_relations
        return await _query_relations(self.db, self.project_id, name)

    async def _query_chapter_summary(self, chapter_num: int) -> str:
        from app.services.chapter_tools import _query_chapter_summary
        return await _query_chapter_summary(self.db, self.project_id, chapter_num)

    async def _get_outline_for_chapter(self, chapter_num: int) -> str:
        ol = (await self.db.execute(
            select(Outline).where(
                Outline.project_id == self.project_id,
                Outline.chapter_number == chapter_num,
            )
        )).scalars().first()
        if not ol:
            return ""
        parts = [f"标题: {ol.title}"]
        if ol.summary:
            parts.append(f"概要: {ol.summary[:300]}")
        if ol.key_points:
            kps = ", ".join(str(k)[:80] for k in ol.key_points[:5])
            parts.append(f"情节点: {kps}")
        if ol.goal:
            parts.append(f"写作目标: {ol.goal[:150]}")
        if ol.emotion:
            parts.append(f"情绪基调: {ol.emotion}")
        return " | ".join(parts)

    async def _query_foreshadows_text(self, filt: str, ch_num: int) -> str:
        service = ForeshadowService(self.db, self.project_id)
        if "must" in filt:
            flist = await service.get_must_resolve_foreshadows(ch_num)
        elif "upcoming" in filt:
            flist = await service.get_pending_resolve_foreshadows(ch_num, 5)
        else:
            flist = await service.list_all(status="planted") + await service.list_all(status="pending")
        if not flist:
            return "无"
        lines = []
        for f in flist[:10]:
            lines.append(f"- [{f.foreshadow_type or '?'}] {f.title}: {(f.content or '')[:100]}")
        return "\n".join(lines)

    async def _query_organization(self, name: str) -> str:
        from app.services.chapter_tools import _query_organization
        return await _query_organization(self.db, self.project_id, name)

    async def _query_timeline(self, query: str, ch_num: int) -> str:
        from app.services.chapter_tools import _query_plot_timeline
        kw = query.strip()
        return await _query_plot_timeline(
            self.db, self.project_id, ch_num,
            keyword=kw if kw else "",
            from_chapter=max(1, ch_num - 20),
            to_chapter=ch_num - 1,
        )

    async def _get_world_settings_text(self) -> str:
        from app.models.world import WorldSetting
        p = (await self.db.execute(
            select(Project).where(Project.id == self.project_id)
        )).scalar_one_or_none()
        parts = []
        if p:
            if p.world_time_period:
                parts.append(f"时间: {p.world_time_period[:200]}")
            if p.world_location:
                parts.append(f"地点: {p.world_location[:200]}")
            if p.world_atmosphere:
                parts.append(f"氛围: {p.world_atmosphere[:200]}")
            if p.world_rules:
                parts.append(f"规则: {p.world_rules[:200]}")
        ws = (await self.db.execute(
            select(WorldSetting).where(WorldSetting.project_id == self.project_id)
        )).scalars().all()
        for w in ws[:5]:
            parts.append(f"[{w.category}] {w.name}: {w.content[:150]}")
        return "\n".join(parts) if parts else ""


    async def generate_chapter(
        self, chapter_id: int, ai_client: AIClient = None,
        overrides: dict = None,
    ) -> dict:
        """非流式生成章节（Planner + Writer 两阶段流程）

        overrides: 批量生成等场景的可选覆盖项，支持键：
            - narrative_pov / narrative_perspective: 叙事视角
            - target_word_count: 目标字数（int）
            - style_config: 写作风格配置 dict（从 WritingStyle.config 取）
            - style_name: 风格名（展示用）
            - use_legacy: 设为 True 回退旧 tool-calling 流程
        """
        chapter, project = await self._get_chapter_and_project(chapter_id)
        await self._validate_generation(chapter)

        if not ai_client:
            ai_client = await self._get_ai_client(project)

        mode, skill_name = self._determine_generation_mode(chapter)
        chapter.status = "generating"
        await self.db.commit()

        try:
            # 构建基本上下文（只取大纲概要，不加载全量数据）
            context = {"chapter_number": chapter.chapter_number,
                       "chapter_title": chapter.title or ""}
            if project:
                context["project_title"] = project.title or ""
                context["target_word_count"] = project.target_word_count or 3000
                context["narrative_pov"] = project.narrative_pov or "第三人称"
                context["narrative_perspective"] = context["narrative_pov"]
            # 应用覆盖项
            if overrides:
                if overrides.get("narrative_pov"):
                    context["narrative_pov"] = overrides["narrative_pov"]
                    context["narrative_perspective"] = overrides["narrative_pov"]
                if overrides.get("target_word_count"):
                    context["target_word_count"] = overrides["target_word_count"]
                if overrides.get("style_config"):
                    import json as _json
                    context["writing_style"] = _json.dumps(overrides["style_config"], ensure_ascii=False)
                if overrides.get("style_name"):
                    context["style_name"] = overrides["style_name"]
                if overrides.get("style_custom_prompt"):
                    context["style_custom_prompt"] = overrides["style_custom_prompt"]

            # ===== Phase 1: Planner（判断需要哪些资料） =====
            use_legacy = (overrides or {}).get("use_legacy", False)
            chapter_data = ""
            if not use_legacy:
                try:
                    chapter_data = await self._run_planner_and_fetch(
                        chapter, project, context, ai_client
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"[planner] Planner 失败，回退旧流程: {e}")
                    use_legacy = True

            if use_legacy:
                # 回退：全量构建上下文 + 适配新 Writer prompt
                # 新 prompt（chapter_generation_one_to_one_next 等）使用 {chapter_data} 单一变量，
                # 需要将 build_chapter_context 的分散字段打包为一个格式化字符串。
                context = await self.context_service.build_chapter_context(chapter, project)
                if overrides:
                    if overrides.get("narrative_pov"):
                        context["narrative_pov"] = overrides["narrative_pov"]
                        context["narrative_perspective"] = overrides["narrative_pov"]
                    if overrides.get("target_word_count"):
                        context["target_word_count"] = overrides["target_word_count"]
                        context["word_count_requirement"] = f"目标{overrides['target_word_count']}字"

                # 将完整上下文打包为 chapter_data（适配新 prompt 的单一变量格式）
                chapter_data = self._format_legacy_context_as_data(context)
                context["chapter_data"] = chapter_data
                context["user_prompt"] = ""

                result = await self.skill_engine.execute_skill(
                    skill_name, ai_client, context,
                )
            else:
                # ===== Phase 3: Writer（新流程，无工具调用） =====
                context["chapter_data"] = chapter_data
                context["user_prompt"] = ""
                result = await self.skill_engine.execute_skill(
                    skill_name, ai_client, context,
                )

            if result.get("error"):
                chapter.status = "draft"
                await self.db.commit()
                return {"error": result["error"]}

            # 提取正文（execute_skill 对章节生成用纯文本 chat）
            content = result.get("content", "")
            # 去除可能的 markdown 残留（AI 偶尔加 ``` 包裹）
            c_stripped = content.strip()
            if c_stripped.startswith("```"):
                lines = content.split("\n")
                if lines and lines[0].strip().startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            # 去除开头的 markdown 标题（AI 偶尔输出「# 第一章 xxx」，系统框架本身已有标题）
            import re as _re
            content = _re.sub(r'^\s*#{1,6}\s*第[一二三四五六七八九十百零\d]+章[^\n]*\n?', '', content)
            content = content.strip()
            if not content or not content.strip():
                chapter.status = "draft"
                await self.db.commit()
                return {"error": "AI 生成内容为空"}

            # 保存
            chapter.content = content
            chapter.word_count = len(content)
            chapter.status = "completed"
            chapter.generation_mode = mode

            # 记录历史
            history = GenerationHistory(
                project_id=self.project_id,
                chapter_id=chapter.id,
                prompt_name=skill_name,
                model_used=result.get("model", ""),
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                duration_ms=result.get("duration_ms", 0),
                response_preview=content[:500],
            )
            self.db.add(history)
            await self.db.commit()

            # 后处理
            await self._post_generation(chapter)

            return {
                "chapter_id": chapter.id,
                "content": content,
                "word_count": chapter.word_count,
                "status": chapter.status,
            }

        except Exception as e:
            chapter.status = "draft"
            await self.db.commit()
            err = str(e)
            # AI 错误友好提示
            if "额度" in err or "401" in err or "api_key" in err.lower():
                return {"error": "AI 服务额度不足或密钥无效，请检查 AI 设置"}
            if "Connection" in err:
                return {"error": "AI 连接失败，请稍后重试"}
            return {"error": err}

    async def generate_chapter_stream(
        self, chapter_id: int, ai_client: AIClient = None
    ) -> AsyncGenerator[str, None]:
        """流式生成章节"""
        chapter, project = await self._get_chapter_and_project(chapter_id)
        await self._validate_generation(chapter)

        if not ai_client:
            ai_client = await self._get_ai_client(project)

        mode, skill_name = self._determine_generation_mode(chapter)
        chapter.status = "generating"
        await self.db.commit()

        try:
            context = await self.context_service.build_chapter_context(chapter, project)
            context["user_prompt"] = f"请根据以上信息，写出第{chapter.chapter_number}章的正文内容。"
            # 将新增的关键事件信息合并到模板已有字段，确保 AI 能用到
            prev_events = context.get("prev_key_events", "")
            if prev_events and prev_events != "暂无":
                existing = context.get("recent_chapters_context", "")
                context["recent_chapters_context"] = (existing + "\n\n" + prev_events).strip("\n")
            # 世界设定注入（让 AI 知道故事发生在什么世界）
            world_setting = context.get("world_setting", "")
            if world_setting and world_setting != "暂无世界设定":
                existing2 = context.get("recent_chapters_context", "")
                context["recent_chapters_context"] = (existing2 + "\n\n" + world_setting).strip("\n")

            result = await self.skill_engine.execute_skill(
                skill_name, ai_client, context, stream=True
            )

            if result.get("error"):
                chapter.status = "draft"
                await self.db.commit()
                yield json.dumps({"error": result["error"]}, ensure_ascii=False)
                return

            full_content = ""
            stream = result["stream"]
            async for token in stream:
                full_content += token
                yield json.dumps({"token": token}, ensure_ascii=False)

            # 保存
            chapter.content = full_content
            chapter.word_count = len(full_content)
            chapter.status = "completed"
            chapter.generation_mode = mode

            history = GenerationHistory(
                project_id=self.project_id,
                chapter_id=chapter.id,
                prompt_name=skill_name,
                duration_ms=0,
                response_preview=full_content[:500],
            )
            self.db.add(history)
            await self.db.commit()

            # 后处理
            await self._post_generation(chapter)

            yield json.dumps({
                "done": True,
                "chapter_id": chapter.id,
                "word_count": chapter.word_count,
            }, ensure_ascii=False)

        except Exception as e:
            chapter.status = "draft"
            await self.db.commit()
            yield json.dumps({"error": str(e)}, ensure_ascii=False)

    async def _post_generation(self, chapter: Chapter):
        """生成后处理"""
        # 1. 自动埋入 pending 伏笔
        await self.foreshadow_service.auto_plant_pending_foreshadows(chapter.chapter_number)

        # 2. 自动生成摘要
        try:
            await self._generate_summary(chapter)
        except Exception as e:
            print(f"[chapter_service] 自动摘要失败: {e}", flush=True)

        # 3. 自动剧情分析
        try:
            await self._auto_analyze(chapter)
        except Exception as e:
            print(f"[chapter_service] 自动剧情分析失败（不影响章节）: {e}", flush=True)

        # 3.5 章节正文按自然段切分入库向量（精细检索）
        try:
            await self._index_chapter_chunks(chapter)
        except Exception as e:
            print(f"[chapter_service] 正文向量切分失败: {e}", flush=True)

        # 4. 卷摘要生成（方案 A：每 VOLUME_SIZE 章自动生成卷摘要）
        try:
            await self._maybe_generate_volume_summary(chapter)
        except Exception as e:
            print(f"[chapter_service] 卷摘要生成失败（不影响章节）: {e}", flush=True)

    async def _generate_summary(self, chapter: Chapter):
        """自动生成章节摘要"""
        ai_client = await AIClient.from_user_config(self.db, self.user_id)
        result = await self.skill_engine.execute_skill(
            "chapter_summary", ai_client,
            {
                "chapter_number": str(chapter.chapter_number),
                "chapter_title": chapter.title,
                "chapter_content": chapter.content[:3000],
                "user_prompt": "请生成摘要。",
            },
        )
        if result.get("json"):
            data = result["json"]
            chapter.summary = data.get("summary", "")
            await self.db.commit()

    async def _auto_analyze(self, chapter: Chapter, on_progress=None):
        """自动剧情分析。"""
        import logging
        logger = logging.getLogger(__name__)

        async def _report(progress: int, message: str):
            if on_progress:
                try: await on_progress(progress, message)
                except Exception: pass

        # 预检：内容不能为空
        content = (chapter.content or "").strip()
        if len(content) < 50:
            logger.warning(f"[analyze] 章节{chapter.chapter_number}内容不足50字，跳过分析")
            return

        # 获取角色信息
        from app.models.character import Character
        await _report(5, "准备分析上下文...")
        result = await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )
        characters = list(result.scalars().all())
        chars_info = ", ".join([f"{c.name}({c.role})" for c in characters])

        existing_fs = await self.foreshadow_service.list_all()
        must_resolve, upcoming, others = [], [], []
        for f in existing_fs:
            entry = f"- {f.title}({f.foreshadow_type or '未分类'})：{f.content[:60]}"
            tgt = f.target_resolve_chapter_number
            if tgt and tgt <= chapter.chapter_number and f.status in ("pending", "planted"):
                must_resolve.append(entry + f" [应于第{tgt}章回收]")
            elif tgt and tgt - chapter.chapter_number <= 3 and f.status in ("pending", "planted"):
                upcoming.append(entry + f" [计划第{tgt}章回收]")
            else:
                others.append(entry)
        fs_layered = "【本章必须回收】\n" + ("\n".join(must_resolve) if must_resolve else "无") +                      "\n【即将到期】\n" + ("\n".join(upcoming) if upcoming else "无") +                      "\n【其他伏笔】\n" + ("\n".join(others[:10]) if others else "无")

        # 章节正文通过 system_prompt 的 {chapter_content} / {content} 注入，不重复放入 user_prompt
        chapter_text = (chapter.content or "")[:5000]
        user_prompt = "请分析这个章节，特别注意是否自然回收了「本章必须回收」的伏笔。"

        ai_client = await AIClient.from_user_config(self.db, self.user_id)
        await _report(10, "AI 正在分析章节剧情...")
        result = await self.skill_engine.execute_skill(
            "plot_analysis", ai_client,
            {
                "chapter_number": str(chapter.chapter_number),
                "chapter_title": chapter.title,
                "word_count": str(chapter.word_count),
                "existing_foreshadows": fs_layered,
                "characters_info": chars_info,
                "chapter_content": chapter_text,
                "user_prompt": user_prompt,
            },
        )
        if result.get("error"):
            # AI 调用本身失败（非 JSON 问题）→ 仍保存 raw_response 便于调试
            analysis = PlotAnalysis(
                project_id=self.project_id, chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                suggestions=["⚠️ 分析失败：" + str(result["error"])[:200]],
                raw_response=result.get("content", ""),
            )
            self.db.add(analysis)
            await self.db.commit()
            raise RuntimeError(f"剧情分析 AI 调用失败: {result['error']}")

        if result.get("json"):
            analysis_data = result["json"]
            await _report(55, "分析完成，正在保存结果...")

            # 字段兼容层：统一 DB 提示词字段名 → 代码期望的字段名
            # hooks：DB 返回 list[{type,content,strength}]，兼容 dict 格式
            hooks_raw = analysis_data.get("hooks", {})
            if isinstance(hooks_raw, list):
                hooks_data = {}
                for h in hooks_raw:
                    if isinstance(h, dict):
                        htype = h.get("type", "general")
                        hooks_data[htype] = h.get("content", h.get("keyword", ""))
                    elif isinstance(h, str):
                        hooks_data["general"] = h
            else:
                hooks_data = hooks_raw
            # conflict：DB 返回单对象 {types,parties,...}，转成数组格式
            conflicts_data = analysis_data.get("conflicts", [])
            conflict_types_data = analysis_data.get("conflict_types", [])
            if not conflicts_data:
                single_conflict = analysis_data.get("conflict", {})
                if isinstance(single_conflict, dict):
                    conflicts_data = [single_conflict]
                    # 提取 types 到 conflict_types
                    ct = single_conflict.get("types", [])
                    if isinstance(ct, list) and not conflict_types_data:
                        conflict_types_data = ct
            # scores → quality_scores
            quality_scores_data = analysis_data.get("quality_scores") or analysis_data.get("scores") or {}
            # plot_points → key_plot_points
            key_plot_points_data = analysis_data.get("key_plot_points") or analysis_data.get("plot_points") or []
            # emotional_arc → emotional_curve / emotion_curve
            emotional_curve_data = analysis_data.get("emotional_curve") or analysis_data.get("emotional_arc") or analysis_data.get("emotion_curve") or {}

            # 保存分析结果
            analysis = PlotAnalysis(
                project_id=self.project_id,
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                hooks=hooks_data,
                foreshadows=analysis_data.get("foreshadows", []),
                conflicts=conflicts_data,
                conflict_types=conflict_types_data,
                emotion_curve=analysis_data.get("emotion_curve", emotional_curve_data if isinstance(emotional_curve_data, list) else []),
                emotional_curve=emotional_curve_data if isinstance(emotional_curve_data, dict) else {},
                character_states=analysis_data.get("character_states", []),
                organization_states=analysis_data.get("organization_states", []),
                key_plot_points=key_plot_points_data,
                scenes=analysis_data.get("scenes", []),
                plot_stage=analysis_data.get("plot_stage", ""),
                dialogue_ratio=analysis_data.get("dialogue_ratio", 0),
                description_ratio=analysis_data.get("description_ratio", 0),
                pacing=analysis_data.get("pacing", ""),
                quality_scores=quality_scores_data,
                consistency_issues=analysis_data.get("consistency_issues", []),
                suggestions=analysis_data.get("suggestions", []),
                analysis_report=generate_analysis_summary(analysis_data),
                raw_response=result.get("content", ""),
            )
            self.db.add(analysis)
            await _report(62, "正在更新章节质量评分...")

            # 更新章节质量评分
            chapter.quality_score = quality_scores_data.get("overall")
            chapter.quality_detail = quality_scores_data

            # 质量告警检测
            alert_parts = []
            overall = quality_scores_data.get("overall", 10)
            coherence = quality_scores_data.get("coherence", 10)
            consistency_issues = analysis_data.get("consistency_issues", [])
            if overall < 5:
                alert_parts.append("low_score")
            if coherence < 4:
                alert_parts.append("low_coherence")
            if consistency_issues and isinstance(consistency_issues, list) and len(consistency_issues) > 0:
                alert_parts.append("consistency_issue")
            chapter.quality_alert = ",".join(alert_parts) if alert_parts else ""

            await self.db.commit()
            await _report(70, "正在同步伏笔状态...")

            # 重新分析前清理旧的分析伏笔（避免重复分析导致堆积），再同步新状态
            try:
                await self.foreshadow_service.clean_analysis_foreshadows(chapter.chapter_number)
            except Exception as e:
                print(f"[chapter_service] 清理旧分析伏笔失败（忽略）: {e}", flush=True)

            # 更新伏笔状态
            await self.foreshadow_service.auto_update_from_analysis(
                analysis_data, chapter.chapter_number
            )
            await _report(78, "正在提取记忆片段...")

            # 提取记忆
            await self._extract_memories(chapter, analysis_data)
            await _report(86, "正在更新角色心理状态...")

            # 回写角色心理状态（让 mental_state 随章节自动更新）
            await self._update_character_states(analysis_data)

            # 角色状态全面更新（#14：生死/心理/关系亲密度/组织成员，带章节防回退）
            try:
                from app.services.character_state_update_service import CharacterStateUpdateService
                csu = CharacterStateUpdateService(self.db, self.project_id)
                await csu.update_from_analysis(
                    analysis_data.get("character_states", []),
                    chapter_id=chapter.id,
                    chapter_number=chapter.chapter_number,
                )
                # 自动生成 CharacterChangeLog
                await self._create_character_change_logs(analysis_data, chapter.chapter_number)
            except Exception:
                pass
            await _report(92, "正在更新角色关系...")

            # 增量更新角色关系（分析结果里若提到关系变化）
            try:
                await self._update_relations_from_analysis(analysis_data, chapter.chapter_number)
            except Exception:
                pass
            await _report(96, "正在更新角色职业阶段...")

            # 更新角色职业阶段（#19，对标 MuMu career_update_service）
            try:
                from app.services.career_update_service import CareerUpdateService
                cs = CareerUpdateService(self.db, self.project_id)
                await cs.update_from_analysis(
                    analysis_data.get("character_states", []),
                    chapter_id=chapter.id,
                    chapter_number=chapter.chapter_number,
                )
            except Exception:
                pass
            await _report(99, "分析完成")

        else:
            # JSON 解析失败（AI 返回了非 JSON 文本）→ 仍保存 raw_response 便于调试和重试
            analysis = PlotAnalysis(
                project_id=self.project_id, chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                suggestions=["⚠️ 分析数据解析失败，AI 返回的不是合法 JSON。可点击「重新分析」重试。"],
                raw_response=result.get("content", ""),
            )
            self.db.add(analysis)
            await self.db.commit()
            raise RuntimeError("剧情分析数据解析失败：AI 返回的不是合法 JSON 格式")

    async def _index_chapter_chunks(self, chapter: Chapter):
        """将章节正文按自然段切分为 chunk（400-800字+重叠120字），每个 chunk 存入向量库。

        这样向量检索可以精确定位到"第N章某段"而非整章摘要。
        每个 chunk 作为一条 StoryMemory（memory_type='chapter_chunk'）入库。
        """
        content = chapter.content or ""
        if len(content.strip()) < 100:
            return

        from app.services.text_splitter import split_text_to_chunks
        from app.services.memory_vector_service import MemoryVectorService

        chunks = split_text_to_chunks(content, min_chunk_size=250, max_chunk_size=400, overlap_size=80)
        if not chunks:
            return

        # 先删除该章节旧的 chunk 记忆（避免重复）
        existing = (await self.db.execute(
            select(StoryMemory).where(
                StoryMemory.project_id == self.project_id,
                StoryMemory.chapter_id == chapter.id,
                StoryMemory.memory_type == "chapter_chunk",
            )
        )).scalars().all()
        for old in existing:
            await self.db.delete(old)
        await self.db.commit()

        # 每个 chunk 创建一条记忆 + 向量
        chunk_memories = []
        for i, chunk_text in enumerate(chunks):
            m = StoryMemory(
                user_id=self.user_id,
                project_id=self.project_id,
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                memory_type="chapter_chunk",
                title=f"第{chapter.chapter_number}章 片段{i+1}/{len(chunks)}",
                content=chunk_text[:500],
                importance=0.6,
                tags=[f"chunk_{i+1}", f"第{chapter.chapter_number}章"],
            )
            self.db.add(m)
            chunk_memories.append(m)
        await self.db.commit()

        # 批量写入向量
        if chunk_memories and self.user_id:
            try:
                ai_client = await AIClient.from_user_config(self.db, self.user_id)
                vs = MemoryVectorService(ai_client)
                for m in chunk_memories:
                    vid = await vs.add_memory(
                        user_id=self.user_id, project_id=self.project_id, memory_id=m.id,
                        content=m.content, memory_type="chapter_chunk",
                        title=m.title, importance=m.importance,
                        chapter_number=chapter.chapter_number,
                    )
                    if vid:
                        m.vector_id = vid
                await self.db.commit()
                print(f"[chapter_service] 第{chapter.chapter_number}章切分为 {len(chunks)} 个 chunk 并已向量化", flush=True)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"[chapter_service] chunk 向量化失败（不影响主流程）: {e}")

    async def _maybe_generate_volume_summary(self, chapter: Chapter):
        """卷摘要自动生成（方案 A：每 VOLUME_SIZE 章生成一个卷摘要）。

        触发条件：当前章节号是 VOLUME_SIZE 的整数倍（如第10、20、30章）。
        卷摘要存入 StoryMemory（memory_type='volume_summary'），供后续章节上下文注入。
        """
        vol_size = settings.VOLUME_SIZE
        ch_num = chapter.chapter_number or 0
        if ch_num < vol_size or ch_num % vol_size != 0:
            return  # 不是卷末章，跳过

        vol_index = ch_num // vol_size  # 第几卷（1-based）
        vol_start = (vol_index - 1) * vol_size + 1
        vol_end = ch_num

        # 检查是否已有该卷摘要（避免重复生成）
        existing = await self.db.scalar(
            select(StoryMemory.id).where(
                StoryMemory.project_id == self.project_id,
                StoryMemory.memory_type == "volume_summary",
                StoryMemory.chapter_number == vol_end,
            )
        )
        if existing:
            return

        print(f"[chapter_service] 第{vol_end}章完成，开始生成第{vol_index}卷摘要（第{vol_start}-{vol_end}章）", flush=True)

        # 收集本卷各章摘要和关键情节点
        chapters = (await self.db.execute(
            select(Chapter).where(
                Chapter.project_id == self.project_id,
                Chapter.chapter_number >= vol_start,
                Chapter.chapter_number <= vol_end,
                Chapter.status == "completed",
            ).order_by(Chapter.chapter_number)
        )).scalars().all()

        if len(chapters) < vol_size // 2:
            return  # 章节数太少，不生成

        chapters_summary_parts = []
        key_plot_parts = []
        for ch in chapters:
            summary = ch.summary or "(无摘要)"
            chapters_summary_parts.append(f"第{ch.chapter_number}章 {ch.title or ''}：{summary}")
            # 从 PlotAnalysis 提取关键情节点
            analysis = (await self.db.execute(
                select(PlotAnalysis).where(
                    PlotAnalysis.project_id == self.project_id,
                    PlotAnalysis.chapter_number == ch.chapter_number,
                ).order_by(PlotAnalysis.id.desc())
            )).scalars().first()
            if analysis and analysis.key_plot_points:
                kps = analysis.key_plot_points if isinstance(analysis.key_plot_points, list) else []
                for kp in kps[:3]:
                    text = kp if isinstance(kp, str) else kp.get("event", kp.get("description", str(kp)))
                    key_plot_parts.append(f"第{ch.chapter_number}章：{text}")

        chapters_summary = "\n".join(chapters_summary_parts)
        key_plot_points = "\n".join(key_plot_parts) if key_plot_parts else "暂无"

        # 调用 AI 生成卷摘要
        try:
            ai_client = await AIClient.from_user_config(self.db, self.user_id)
            result = await self.skill_engine.execute_skill(
                "volume_summary", ai_client,
                {
                    "chapters_summary": chapters_summary[:4000],
                    "key_plot_points": key_plot_points[:2000],
                    "user_prompt": f"请为第{vol_start}-{vol_end}章生成卷摘要。",
                },
            )
            if result.get("json"):
                data = result["json"]
                vol_summary = data.get("volume_summary", "")
                if vol_summary:
                    # 存入 StoryMemory
                    m = StoryMemory(
                        user_id=self.user_id,
                        project_id=self.project_id,
                        chapter_id=chapter.id,
                        chapter_number=vol_end,  # 标记到卷末章
                        memory_type="volume_summary",
                        title=f"第{vol_start}-{vol_end}章卷摘要",
                        content=vol_summary[:1000],
                        importance=0.9,  # 高重要度
                        tags=[f"vol_{vol_index}", f"第{vol_start}-{vol_end}章"],
                    )
                    self.db.add(m)
                    await self.db.commit()

                    # 同步写入向量库
                    if self.user_id:
                        try:
                            from app.services.memory_vector_service import MemoryVectorService
                            vs = MemoryVectorService(ai_client)
                            vid = await vs.add_memory(
                                user_id=self.user_id, project_id=self.project_id, memory_id=m.id,
                                content=m.content, memory_type="volume_summary",
                                title=m.title, importance=m.importance,
                                chapter_number=vol_end,
                            )
                            if vid:
                                m.vector_id = vid
                                await self.db.commit()
                        except Exception:
                            pass

                    print(f"[chapter_service] 第{vol_index}卷摘要已生成（第{vol_start}-{vol_end}章）", flush=True)
            elif result.get("content"):
                # JSON 解析失败但有内容，直接用 raw content
                vol_summary = result["content"][:1000]
                m = StoryMemory(
                    user_id=self.user_id,
                    project_id=self.project_id,
                    chapter_id=chapter.id,
                    chapter_number=vol_end,
                    memory_type="volume_summary",
                    title=f"第{vol_start}-{vol_end}章卷摘要",
                    content=vol_summary,
                    importance=0.9,
                    tags=[f"vol_{vol_index}"],
                )
                self.db.add(m)
                await self.db.commit()
                print(f"[chapter_service] 第{vol_index}卷摘要已生成（raw content）", flush=True)
        except Exception as e:
            print(f"[chapter_service] 卷摘要 AI 调用失败: {e}", flush=True)

    async def _update_character_states(self, analysis_data: dict):
        """根据剧情分析结果，自动更新角色的 mental_state（当前心理）。

        对标 MuMuAINovel 的角色状态更新：从 character_states 提取状态变化，
        按角色名匹配并更新 Character.mental_state 字段。
        """
        from app.models.character import Character
        char_states = analysis_data.get("character_states", [])
        if not char_states:
            return
        # 加载项目角色，建名字→Character 映射
        chars = (await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )).scalars().all()
        name_map = {c.name: c for c in chars}
        updated = 0
        for state in char_states:
            if not isinstance(state, dict):
                continue
            # 兼容多种字段名：character / character_name / name
            name = state.get("character") or state.get("character_name") or state.get("name")
            if not name:
                continue
            # 模糊匹配（支持"林轩"匹配到角色"林轩"）
            char = name_map.get(name) or next((c for c in chars if name in c.name or c.name in name), None)
            if not char:
                continue
            # 取最新的心理状态描述
            new_state = state.get("state_after") or state.get("mental_change") or state.get("current_state") or state.get("change")
            if new_state and str(new_state).strip():
                char.mental_state = str(new_state).strip()[:50]
                updated += 1
        if updated:
            await self.db.commit()

    async def _create_character_change_logs(self, analysis_data: dict, chapter_number: int):
        """根据分析结果中 character_states 的变化，自动创建 CharacterChangeLog。
        
        只记录 analysis 中明确提到的变化字段（survival_status/mental_change/relation_change 等），
        不记录完整快照（快照留给用户手动添加时保存）。
        """
        from app.models.character_change_log import CharacterChangeLog
        char_states = analysis_data.get("character_states", [])
        if not char_states:
            return
        chars = (await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )).scalars().all()
        name_map = {c.name: c for c in chars}
        created = 0
        for state in char_states:
            if not isinstance(state, dict):
                continue
            name = state.get("character") or state.get("character_name") or state.get("name")
            if not name:
                continue
            char = name_map.get(name) or next((c for c in chars if name in c.name or c.name in name), None)
            if not char:
                continue
            # 提取变化字段
            changed = {}
            survival = state.get("survival_status") or state.get("status_change")
            mental = state.get("mental_change") or state.get("state_after") or state.get("current_state")
            relation = state.get("relation_change")
            arc = state.get("arc_progress") or state.get("arc_stage")
            ability = state.get("ability_change")
            career = state.get("career_changes")
            
            if survival: changed["status"] = str(survival)[:50]
            if mental: changed["mental_state"] = str(mental)[:50]
            if relation: changed["relation"] = str(relation)[:80]
            if arc: changed["arc"] = str(arc)[:80]
            if ability: changed["ability"] = str(ability)[:80]
            if career: changed["career"] = str(career)[:80]
            if not changed:
                continue
            # 构建摘要
            summary_parts = [f"{name}"]
            for k, v in changed.items():
                field_label = {"status":"状态","mental_state":"心理","relation":"关系","arc":"角色弧","ability":"能力","career":"职业"}.get(k, k)
                summary_parts.append(f"{field_label}→{v[:20]}")
            summary = "；".join(summary_parts)
            # 保存当前快照
            snapshot = {c.name: getattr(char, c.name) for c in char.__table__.columns
                       if c.name not in ('created_at', 'updated_at')}
            self.db.add(CharacterChangeLog(
                project_id=self.project_id,
                character_id=char.id,
                chapter_number=chapter_number,
                changed_fields=changed,
                snapshot=snapshot,
                summary=f"第{chapter_number}章：{summary}",
            ))
            created += 1
        if created:
            await self.db.commit()

    async def _update_relations_from_analysis(self, analysis_data: dict, chapter_number: int = 0):
        """根据剧情分析结果，增量更新角色关系并写入 RelationChangeLog。

        若分析返回 character_states 里含 relation_change，或顶层 relation_changes，
        解析出涉及的角色对和关系类型，记录变化日志后 upsert 到 CharacterRelation 表。
        """
        from app.models.character import CharacterRelation
        from app.models.relation_change_log import RelationChangeLog

        # 收集关系变化项
        rel_changes = list(analysis_data.get("relation_changes") or [])
        for state in (analysis_data.get("character_states") or []):
            if isinstance(state, dict) and state.get("relation_change"):
                rel_changes.append({
                    "character": state.get("character") or state.get("character_name"),
                    "change": state.get("relation_change"),
                })
        if not rel_changes:
            return

        chars = (await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )).scalars().all()
        if len(chars) < 2:
            return
        name_map = {c.name: c for c in chars}

        # 已有关系
        existing = (await self.db.execute(
            select(CharacterRelation).where(CharacterRelation.project_id == self.project_id)
        )).scalars().all()
        existing_map: dict[tuple, CharacterRelation] = {}
        for r in existing:
            existing_map[(r.from_character_id, r.to_character_id)] = r
            existing_map[(r.to_character_id, r.from_character_id)] = r

        updated = 0
        for ch in rel_changes:
            if not isinstance(ch, dict):
                continue
            desc = str(ch.get("change") or ch.get("description") or "")
            if not desc:
                continue
            mentioned = [c for c in chars if c.name in desc]
            if len(mentioned) < 2:
                continue
            a, b = mentioned[0], mentioned[1]
            key = (a.id, b.id)
            existing_rel = existing_map.get(key)
            
            if existing_rel:
                # 记录变化日志
                old_intimacy = existing_rel.intimacy or 0
                # 尝试从描述中推断亲密度变化
                intimacy_delta = 0
                desc_lower = desc.lower()
                if any(kw in desc_lower for kw in ('增进', '亲近', '好感', '信任', '和解', '结盟', '同盟', '朋友')):
                    intimacy_delta = 10
                elif any(kw in desc_lower for kw in ('恶化', '疏远', '背叛', '仇恨', '敌对', '决裂', '反目')):
                    intimacy_delta = -10
                new_intimacy = max(-100, min(100, old_intimacy + intimacy_delta))
                
                if intimacy_delta != 0:
                    old_snapshot = {c.name: getattr(existing_rel, c.name) for c in existing_rel.__table__.columns
                                   if c.name not in ('created_at', 'updated_at')}
                    existing_rel.intimacy = new_intimacy
                    # 更新 relation_type 如果描述里有明确关系词
                    relation_keywords = {'师徒': '师徒', '恋人': '恋人', '父子': '父子', '母女': '母女',
                                         '兄弟': '兄弟', '姐妹': '姐妹', '宿敌': '宿敌', '同盟': '同盟',
                                         '同门': '同门', '雇佣': '雇佣', '救命': '救命恩人', '仇敌': '仇敌'}
                    for kw, rtype in relation_keywords.items():
                        if kw in desc:
                            existing_rel.relation_type = rtype
                            break
                    self.db.add(RelationChangeLog(
                        project_id=self.project_id,
                        relation_id=existing_rel.id,
                        chapter_number=chapter_number,
                        changed_fields={"intimacy": {"old": old_intimacy, "new": new_intimacy}},
                        snapshot={c.name: getattr(existing_rel, c.name) for c in existing_rel.__table__.columns
                                 if c.name not in ('created_at', 'updated_at')},
                        summary=f"第{chapter_number}章：{a.name}与{b.name}{desc[:80]}",
                    ))
                    updated += 1
            else:
                # 不存在的关系，新建
                rtype = "相识"
                relation_keywords = {'师徒': '师徒', '恋人': '恋人', '父子': '父子', '母女': '母女',
                                     '兄弟': '兄弟', '姐妹': '姐妹', '宿敌': '宿敌', '同盟': '同盟',
                                     '同门': '同门', '雇佣': '雇佣', '救命': '救命恩人', '仇敌': '仇敌'}
                for kw, rtype_kw in relation_keywords.items():
                    if kw in desc:
                        rtype = rtype_kw
                        break
                rel = CharacterRelation(
                    project_id=self.project_id,
                    from_character_id=a.id, to_character_id=b.id,
                    relation_type=rtype, description=desc[:200],
                    intimacy=0, status="active",
                )
                self.db.add(rel)
                await self.db.flush()
                # 记录新增日志
                self.db.add(RelationChangeLog(
                    project_id=self.project_id,
                    relation_id=rel.id,
                    chapter_number=chapter_number,
                    changed_fields={"relation_type": rtype},
                    snapshot={c.name: getattr(rel, c.name) for c in rel.__table__.columns
                             if c.name not in ('created_at', 'updated_at')},
                    summary=f"第{chapter_number}章：{a.name}与{b.name}建立{rtype}关系",
                ))
                existing_map[key] = rel
                updated += 1
                
        if updated:
            await self.db.commit()

    async def _extract_memories(self, chapter: Chapter, analysis_data: dict):
        """从分析结果提取 6 类记忆（对标 MuMuAINovel extract_memories_from_analysis）。

        类型：summary(章节摘要) / plot(关键情节) / character(角色变化) /
              foreshadow(伏笔) / hook(钩子) / conflict(冲突)

        记忆同步写入向量库（ChromaDB），供后续章节生成时语义召回。
        重新分析时会先清理该章节这 6 类旧记忆（DB + 向量库），避免堆积。
        chapter_chunk / volume_summary 由其他流程产生，不在清理范围。
        """
        def _mk(mtype, content, importance=0.6, title="", related=None):
            if not content or not str(content).strip():
                return None
            return StoryMemory(
                user_id=self.user_id,
                project_id=self.project_id, chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                memory_type=mtype,
                title=title or "",
                content=str(content)[:500],
                importance=importance,
                related_characters=related or [],
            )

        # 清理该章节的分析类旧记忆（DB + 向量库），避免重新分析堆积
        analysis_memory_types = ("summary", "plot", "character", "foreshadow", "hook", "conflict")
        old_mems = (await self.db.execute(
            select(StoryMemory).where(
                StoryMemory.project_id == self.project_id,
                StoryMemory.chapter_id == chapter.id,
                StoryMemory.memory_type.in_(analysis_memory_types),
            )
        )).scalars().all()
        if old_mems:
            # 先清理向量库（按 memory_id 逐条删）
            if self.user_id:
                try:
                    from app.services.memory_vector_service import MemoryVectorService
                    ai_client = await AIClient.from_user_config(self.db, self.user_id)
                    vs = MemoryVectorService(ai_client)
                    for m in old_mems:
                        await vs.delete_memory(self.user_id, self.project_id, m.id)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"[memory] 清理旧向量失败（不影响）: {e}")
            # 再删 DB 记录
            for m in old_mems:
                await self.db.delete(m)
            await self.db.commit()

        memories = []

        # 1. 章节摘要（最重要，供后续章节快速回顾）
        if chapter.summary:
            memories.append(_mk("summary", f"第{chapter.chapter_number}章摘要：{chapter.summary}", 0.8, title=f"第{chapter.chapter_number}章摘要"))

        # 2. 关键情节点
        for point in analysis_data.get("key_plot_points", []):
            content = point if isinstance(point, str) else point.get("event", point.get("description", str(point)))
            memories.append(_mk("plot", content, 0.75, title="关键情节"))

        # 3. 角色状态变化（心理/关系/能力）
        for state in analysis_data.get("character_states", []):
            if isinstance(state, dict):
                parts = []
                char_name = ""
                for k in ("character_name", "character"):
                    if state.get(k):
                        char_name = str(state[k])
                        parts.append(char_name); break
                for k in ("mental_change", "state_after", "relation_change", "ability_change"):
                    if state.get(k):
                        parts.append(f"{k.replace('_','')}={state[k]}")
                if len(parts) > 1:
                    memories.append(_mk("character", "，".join(parts), 0.65, title=f"{char_name}状态变化", related=[char_name] if char_name else []))

        # 4. 伏笔（埋下/回收）
        for fs in analysis_data.get("foreshadows", []):
            if isinstance(fs, dict):
                action = fs.get("action", fs.get("type", ""))
                title = fs.get("title", fs.get("description", str(fs)))
                memories.append(_mk("foreshadow", f"[{action}] {title}", 0.7, title=title[:200]))
            elif isinstance(fs, str):
                memories.append(_mk("foreshadow", fs, 0.7, title="伏笔"))

        # 5. 钩子（吸引读者的悬念点）
        hooks = analysis_data.get("hooks", {})
        if isinstance(hooks, dict):
            hooks = hooks.get("hooks", hooks.get("items", []))
        for hook in (hooks if isinstance(hooks, list) else []):
            if isinstance(hook, dict):
                memories.append(_mk("hook", hook.get("description", hook.get("content", str(hook))), 0.55, title="悬念钩子"))
            elif isinstance(hook, str):
                memories.append(_mk("hook", hook, 0.55, title="悬念钩子"))

        # 6. 冲突
        for conflict in analysis_data.get("conflicts", []):
            if isinstance(conflict, dict):
                desc = conflict.get("description", conflict.get("type", str(conflict)))
                progress = conflict.get("resolution_progress", conflict.get("status", ""))
                memories.append(_mk("conflict", f"{desc}（{progress}）" if progress else desc, 0.6, title="冲突"))
            elif isinstance(conflict, str):
                memories.append(_mk("conflict", conflict, 0.6, title="冲突"))

        valid = [m for m in memories if m is not None]
        for m in valid:
            self.db.add(m)
        await self.db.commit()

        # 同步写入向量库（失败不阻塞主流程）
        if valid and self.user_id:
            try:
                from app.services.memory_vector_service import MemoryVectorService
                ai_client = await AIClient.from_user_config(self.db, self.user_id)
                vs = MemoryVectorService(ai_client)
                for m in valid:
                    vid = await vs.add_memory(
                        user_id=self.user_id, project_id=self.project_id, memory_id=m.id,
                        content=m.content, memory_type=m.memory_type, title=m.title,
                        importance=m.importance, chapter_number=m.chapter_number,
                    )
                    if vid:
                        m.vector_id = vid
                await self.db.commit()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"[memory] 批量写入向量失败（不影响主流程）: {e}")

    async def clear_chapter_content(self, chapter_id: int):
        """清空章节内容以重新生成"""
        result = await self.db.execute(select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == self.project_id,
        ))
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise ValueError("章节不存在")
        chapter.content = ""
        chapter.word_count = 0
        chapter.status = "draft"
        chapter.summary = ""
        chapter.quality_score = None
        chapter.quality_detail = {}
        await self.db.commit()
        return chapter