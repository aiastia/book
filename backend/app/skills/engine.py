import asyncio
"""Skill 执行引擎"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.skill import Skill, SkillConfig
from app.core.ai_client import AIClient
from app.core.config import settings


# ===== 上下文自动注入 =====

def _fmt_project(ctx: dict) -> str:
    parts = []
    if ctx.get("title"): parts.append(f"书名：{ctx['title']}")
    if ctx.get("genre"): parts.append(f"题材：{ctx['genre']}")
    if ctx.get("synopsis"): parts.append(f"简介：{ctx['synopsis']}")
    pov = ctx.get("narrative_perspective") or ctx.get("narrative_pov", "")
    if pov: parts.append(f"叙事视角：{pov}")
    cnt = ctx.get("chapter_count", "")
    if cnt: parts.append(f"章节数：{cnt}")
    return "\n".join(parts)

def _fmt_previous(ctx: dict) -> str:
    parts = []
    prev = ctx.get("continuation_point", "")
    if prev: parts.append(f"上章结尾：{prev[:500]}")
    content = ctx.get("previous_chapter_content", "")
    if content: parts.append(f"上章正文：{content[:800]}")
    summary = ctx.get("previous_chapter_summary") or ctx.get("previous_summary", "")
    if summary: parts.append(f"上章摘要：{summary[:300]}")
    return "\n".join(parts) if parts else ""

def _mk(label, keys, fn):
    return (label, fn, keys)

_CONTEXT_BLOCKS = {
    "project":    _mk("【小说信息】", ["title","genre","synopsis","narrative_perspective","narrative_pov","chapter_count"], _fmt_project),
    "world":      _mk("【世界观】", ["world_info"], lambda c: str(c.get("world_info",""))),
    "characters": _mk("【角色信息】", ["characters_info"], lambda c: str(c.get("characters_info",""))),
    "orgs":       _mk("【组织与势力】", ["organizations_info","chapter_careers"], lambda c: str(c.get("organizations_info") or c.get("chapter_careers",""))),
    "outline":    _mk("【本章大纲】", ["chapter_outline","expansion_plan"], lambda c: str(c.get("chapter_outline") or c.get("expansion_plan",""))),
    "previous":   _mk("【前章衔接】", ["continuation_point","previous_chapter_content","previous_chapter_summary","previous_summary"], _fmt_previous),
    "foreshadow": _mk("【伏笔提醒】", ["foreshadow_reminders","pending_foreshadows"], lambda c: str(c.get("foreshadow_reminders") or c.get("pending_foreshadows",""))),
    "memory":     _mk("【相关记忆】", ["relevant_memories","recalled_memories"], lambda c: str(c.get("relevant_memories") or c.get("recalled_memories",""))),
    "recent":     _mk("【近期脉络】", ["recent_outlines","recent_expansion_plans","recent_chapters_context"], lambda c: str(c.get("recent_outlines") or c.get("recent_expansion_plans") or c.get("recent_chapters_context",""))),
    "quality":    _mk("【质量趋势】", ["quality_trends","quality_trends_detail"], lambda c: str(c.get("quality_trends_detail") or c.get("quality_trends",""))),
    "past_outlines": _mk("【已有大纲】", ["recent_outlines_json","existing_chapters"], lambda c: str(c.get("recent_outlines_json") or c.get("existing_chapters",""))),
    "foreshadow_ctx": _mk("【伏笔上下文】", ["foreshadow_context"], lambda c: str(c.get("foreshadow_context",""))),
}

# skill → 注入的上下文块（前缀匹配）
_SKILL_BLOCKS = {
    "world_core_generate":     ["project","world"],
    "world_detail_generate":   ["project","world"],
    "world_generate":          ["project","world"],
    "career_system_generation":["project","world"],
    "organization_generate":   ["project","world","characters"],
    "single_organization_":    ["project","world","characters"],
    "auto_organization_":      ["project","world","characters"],
    "characters_batch_generation": ["project","world","orgs"],
    "character_generate":      ["project","world","orgs"],
    "character_relations_generate": ["project","characters"],
    "outline_create":          ["project","world","characters","orgs","past_outlines","foreshadow_ctx"],
    "outline_continue":        ["project","world","characters","orgs","recent","past_outlines","foreshadow_ctx"],
    "outline_expand_":         ["project","world","characters","orgs","outline"],
    "chapter_generation_":     ["project","world","characters","orgs","outline","previous","foreshadow","memory","recent","quality"],
    "chapter_generate_":       ["project","world","characters","orgs","outline","previous","foreshadow","memory","recent","quality"],
    "chapter_summary":         ["project","outline"],
    "plot_analysis":           ["project","outline","foreshadow"],
    "volume_summary":          ["project","recent"],
    "inspire":                 ["project"],
    "inspiration_":            ["project"],
    "book_import_":            ["project"],
    "foreshadow_plan":         ["project","outline","foreshadow"],
    "ai_denoising":            ["project","outline"],
    "chapter_planner":         ["project"],
    "partial_regenerate":      ["project","outline","characters"],
    "chapter_regeneration_":   ["project","outline","characters"],
    "_default_":               ["project"],
}

def _get_blocks(skill_name: str) -> list[str]:
    for prefix, blocks in _SKILL_BLOCKS.items():
        if prefix == "_default_": continue
        if skill_name == prefix or skill_name.startswith(prefix):
            return blocks
    return _SKILL_BLOCKS["_default_"]

def _inject_context_blocks(context: dict, skill_name: str = "") -> list[dict]:
    needed = _get_blocks(skill_name)
    msgs = []
    for bn in needed:
        if bn not in _CONTEXT_BLOCKS: continue
        label, fn, keys = _CONTEXT_BLOCKS[bn]
        if not any(str(context.get(k,"")).strip() for k in keys):
            continue
        content = fn(context).strip()
        if content:
            msgs.append({"role":"system","content":f"{label}\n{content}"})
    return msgs


class SkillEngine:
    """Skill 插件执行引擎"""

    def __init__(self, db: AsyncSession, user_id: int = None):
        self.db = db
        self.user_id = user_id

    async def get_skill(self, skill_name: str) -> Optional[Skill]:
        result = await self.db.execute(select(Skill).where(Skill.name == skill_name))
        skill = result.scalar_one_or_none()
        if skill:
            return skill

        alt = None
        if "_generate_" in skill_name:
            alt = skill_name.replace("_generate_", "_generation_")
        elif "_generation_" in skill_name:
            alt = skill_name.replace("_generation_", "_generate_")
        if alt:
            result = await self.db.execute(select(Skill).where(Skill.name == alt))
            return result.scalar_one_or_none()
        return None

    async def get_enabled_skills(self, category: str = None) -> list[Skill]:
        q = select(Skill).where(Skill.is_enabled == True)
        if category:
            q = q.where(Skill.category == category)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_user_config(self, skill_id: int) -> Optional[dict]:
        if not self.user_id:
            return None
        result = await self.db.execute(
            select(SkillConfig).where(
                SkillConfig.skill_id == skill_id,
                SkillConfig.user_id == self.user_id
            )
        )
        cfg = result.scalar_one_or_none()
        if cfg:
            return {"is_enabled": cfg.is_enabled, "is_customized": cfg.is_customized, "config": cfg.config}
        return None

    async def execute_skill(
        self,
        skill_name: str,
        ai_client: AIClient,
        context: dict,
        stream: bool = False,
        tools: list[dict] = None,
        tool_executor=None,
    ) -> dict:
        """执行 Skill

        context: 包含执行 Skill 所需的所有上下文数据
        """
        skill = await self.get_skill(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' 不存在"}

        user_cfg = await self.get_user_config(skill.id)
        if user_cfg and not user_cfg["is_enabled"]:
            return {"error": f"Skill '{skill_name}' 已被用户禁用"}

        merged_config = {**skill.config}
        if user_cfg and user_cfg.get("config"):
            merged_config.update(user_cfg["config"])

        system_prompt = skill.system_prompt
        # 只有当用户主动开启了自定义（is_customized=True）且提供了 system_prompt 时才使用用户版本
        if user_cfg and user_cfg.get("is_customized") and user_cfg.get("config", {}).get("system_prompt"):
            system_prompt = user_cfg["config"]["system_prompt"]

        # 替换提示词中的变量（兼容用户模板中直接写的 {变量}）
        for key, value in context.items():
            if isinstance(value, str):
                system_prompt = system_prompt.replace(f"{{{key}}}", value)
        _aliases = {
            "content": context.get("chapter_content", context.get("content", "")),
            "title": context.get("chapter_title", context.get("title", "")),
        }
        for key, value in _aliases.items():
            if isinstance(value, str) and f"{{{key}}}" in system_prompt:
                system_prompt = system_prompt.replace(f"{{{key}}}", value)

        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # ===== 自动注入上下文（按 skill 类型选择性注入）=====
        _injected = _inject_context_blocks(context, skill_name)
        messages.extend(_injected)

        messages.append({"role": "user", "content": str(context.get("user_prompt", ""))})

        model = merged_config.get("model")
        temperature = merged_config.get("temperature")
        if temperature is not None:
            temperature = temperature / 100 if temperature > 2 else temperature
        top_p = merged_config.get("top_p")
        if top_p is not None:
            top_p = top_p / 100 if top_p > 1 else top_p
        max_tokens = merged_config.get("max_tokens")
        if max_tokens is None:
            max_tokens = settings.AI_DEFAULT_MAX_TOKENS
        max_tokens = min(max_tokens, settings.AI_MAX_TOKENS)

        if stream:
            return {
                "stream": ai_client.chat_stream(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    top_p=top_p,
                    max_tokens=max_tokens,
                ),
                "skill": skill,
            }

        is_text_output = skill_name.startswith("chapter_generation") or skill_name == "ai_denoising"
        if is_text_output:
            result = None
            for attempt in range(3):
                if tools and tool_executor:
                    result = await ai_client.chat_with_tools(
                        messages=messages,
                        tools=tools,
                        tool_executor=tool_executor,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens or settings.AI_DEFAULT_MAX_TOKENS,
                    )
                else:
                    result = await ai_client.chat(
                        messages=messages, model=model,
                        temperature=temperature, top_p=top_p,
                        max_tokens=max_tokens or settings.AI_DEFAULT_MAX_TOKENS,
                    )
                if not result.get("error"):
                    break
                err = result.get("error","")
                if "Connection" in err or "connection" in err or "Timeout" in err:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break
        else:
            result = await ai_client.chat_json_retry(
                messages=messages, model=model,
                temperature=temperature,
                max_tokens=max_tokens or settings.AI_DEFAULT_MAX_TOKENS,
            )

        for hook in (skill.post_hooks or []):
            hook_type = hook.get("type")
            if hook_type == "parse_json" and result.get("content"):
                pass

        result["skill_name"] = skill_name
        result["skill_id"] = skill.id
        return result

    async def list_skills(self, category: str = None) -> list[dict]:
        skills = await self.get_enabled_skills(category)
        result = []
        for s in skills:
            user_cfg = await self.get_user_config(s.id)
            result.append({
                "id": s.id,
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
                "category": s.category,
                "skill_type": s.skill_type,
                "is_enabled": user_cfg["is_enabled"] if user_cfg else s.is_enabled,
                "parameters": s.parameters,
            })
        return result
