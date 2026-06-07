"""章节生成服务 - 核心逻辑链路"""
import json
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.outline import Outline
from app.models.plot_analysis import PlotAnalysis
from app.models.story_memory import StoryMemory
from app.models.generation_history import GenerationHistory
from app.services.chapter_context_service import ChapterContextService
from app.services.foreshadow_service import ForeshadowService
from app.skills.engine import SkillEngine
from app.core.ai_client import AIClient
from app.core.config import settings


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
                )
        return AIClient()

    async def generate_chapter(
        self, chapter_id: int, ai_client: AIClient = None
    ) -> dict:
        """非流式生成章节"""
        chapter, project = await self._get_chapter_and_project(chapter_id)
        await self._validate_generation(chapter)

        if not ai_client:
            ai_client = await self._get_ai_client(project)

        mode, skill_name = self._determine_generation_mode(chapter)
        chapter.status = "generating"
        await self.db.commit()

        try:
            # 构建上下文
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

            # 构建工具调用系统（让 AI 按需查询角色/伏笔/物品等）
            from app.services.chapter_tools import get_chapter_tools, make_tool_executor
            tools = get_chapter_tools()
            tool_executor = make_tool_executor(self.db, self.project_id, chapter.chapter_number)

            # 执行 Skill（带工具调用）
            result = await self.skill_engine.execute_skill(
                skill_name, ai_client, context,
                tools=tools, tool_executor=tool_executor,
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

    async def _auto_analyze(self, chapter: Chapter):
        """自动剧情分析"""
        # 获取角色信息
        from app.models.character import Character
        result = await self.db.execute(
            select(Character).where(Character.project_id == self.project_id)
        )
        characters = list(result.scalars().all())
        chars_info = ", ".join([f"{c.name}({c.role})" for c in characters])

        existing_fs = await self.foreshadow_service.list_all()
        # 伏笔分层注入（对标原项目）：让 AI 识别本章是否自然回收了某个伏笔
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

        ai_client = await AIClient.from_user_config(self.db, self.user_id)
        result = await self.skill_engine.execute_skill(
            "plot_analysis", ai_client,
            {
                "chapter_number": str(chapter.chapter_number),
                "chapter_title": chapter.title,
                "word_count": str(chapter.word_count),
                "existing_foreshadows": fs_layered,
                "characters_info": chars_info,
                "chapter_content": chapter.content[:5000],
                "user_prompt": "请分析这个章节，特别注意是否自然回收了「本章必须回收」的伏笔。",
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
                suggestions=analysis_data.get("suggestions", []),
                raw_response=result.get("content", ""),
            )
            self.db.add(analysis)

            # 更新章节质量评分
            chapter.quality_score = quality_scores_data.get("overall")
            chapter.quality_detail = quality_scores_data

            await self.db.commit()

            # 更新伏笔状态
            await self.foreshadow_service.auto_update_from_analysis(
                analysis_data, chapter.chapter_number
            )

            # 提取记忆
            await self._extract_memories(chapter, analysis_data)

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
            except Exception:
                pass

            # 增量更新角色关系（分析结果里若提到关系变化）
            try:
                await self._update_relations_from_analysis(analysis_data)
            except Exception:
                pass

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

    async def _update_relations_from_analysis(self, analysis_data: dict):
        """根据剧情分析结果，增量更新角色关系（轻量，不调 AI）。

        若分析返回 character_states 里含 relation_change，或顶层 relation_changes，
        解析出涉及的角色对和关系类型，upsert 到 CharacterRelation 表。
        """
        from app.models.character import CharacterRelation

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

        # 已有关系（避免重复）
        existing = (await self.db.execute(
            select(CharacterRelation).where(CharacterRelation.project_id == self.project_id)
        )).scalars().all()
        existing_keys = {(r.from_character_id, r.to_character_id, r.relation_type) for r in existing}

        updated = 0
        for ch in rel_changes:
            if not isinstance(ch, dict):
                continue
            desc = str(ch.get("change") or ch.get("description") or "")
            if not desc:
                continue
            # 从描述里尝试匹配两个角色名
            mentioned = [c for c in chars if c.name in desc]
            if len(mentioned) < 2:
                continue
            a, b = mentioned[0], mentioned[1]
            # 简单推断关系类型（取描述里较短的词）
            rtype = desc[:20] if len(desc) <= 20 else "关系变化"
            key = (a.id, b.id, rtype)
            rev_key = (b.id, a.id, rtype)
            if key in existing_keys or rev_key in existing_keys:
                continue
            self.db.add(CharacterRelation(
                project_id=self.project_id,
                from_character_id=a.id, to_character_id=b.id,
                relation_type=rtype, description=desc[:200],
                status="active",
            ))
            existing_keys.add(key)
            updated += 1
        if updated:
            await self.db.commit()

    async def _extract_memories(self, chapter: Chapter, analysis_data: dict):
        """从分析结果提取 6 类记忆（对标 MuMuAINovel extract_memories_from_analysis）。

        类型：summary(章节摘要) / plot(关键情节) / character(角色变化) /
              foreshadow(伏笔) / hook(钩子) / conflict(冲突)

        记忆同步写入向量库（ChromaDB），供后续章节生成时语义召回。
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