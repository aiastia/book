import asyncio
import os
import re
import logging
"""Skill 执行引擎"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.skill import Skill, SkillConfig
from app.core.ai_client import AIClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# 提示词文件目录
_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _resolve_includes(text: str, base_dir: str = None, seen: set = None, user_overrides: dict = None) -> str:
    """解析提示词中的 @include:filename 指令，替换为文件内容。

    支持嵌套 include（最多 5 层），自动检测循环引用。
    user_overrides: {filename: content} 用户自定义的共享模块内容（优先于文件）
    自动将模板中的双花括号 {{ }} 规范化为单花括号，防止 AI 模仿返回无效 JSON。
    """
    if base_dir is None:
        base_dir = _PROMPTS_DIR
    if seen is None:
        seen = set()

    def _replace(m: re.Match) -> str:
        fname = m.group(1).strip()
        if fname in seen:
            return f"[@include 循环引用已截断: {fname}]"
        # 用户自定义优先于文件
        if user_overrides and fname in user_overrides:
            seen.add(fname)
            content = user_overrides[fname]
            # 递归解析嵌套 include
            if len(seen) < 5 and "@include:" in content:
                content = _resolve_includes(content, base_dir, seen, user_overrides)
            return _normalize_braces(content)
        inc_path = os.path.join(base_dir, fname)
        if not os.path.isfile(inc_path):
            return f"[@include 文件不存在: {fname}]"
        seen.add(fname)
        try:
            with open(inc_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            return f"[@include 读取失败: {fname}]"
        # 递归解析嵌套 include，但限制深度
        if len(seen) < 5 and "@include:" in content:
            content = _resolve_includes(content, base_dir, seen, user_overrides)
        return _normalize_braces(content)

    result = re.sub(r"@include:(\S+\.md)", _replace, text)
    return _normalize_braces(result)


def _normalize_braces(text: str) -> str:
    """将模板中的双花括号 {{ }} 规范化为单花括号 { }。"""
    if not text:
        return text
    return text.replace("{{", "{").replace("}}", "}")


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

# skill → 注入的上下文块（前缀匹配，长前缀优先）
# 标记：🔵=初始化管线使用  🟢=页面手动使用  ⚪=内部自动调用
_SKILL_BLOCKS = {
    # 🔵 世界观生成（初始化 step1 + 页面手动）
    "world_core_generate":     ["project","world"],
    "world_detail_generate":   ["project","world"],
    "world_generate":          ["project","world"],
    # 🔵🟢 地点/物品生成（初始化 step4-5 + 页面手动）
    "locations_generate":      ["project","world"],
    "items_generate":          ["project","world"],
    # 🔵 职业体系生成（初始化 step2）
    "career_system_generation":["project","world"],
    # 🔵 组织生成（初始化 step6 + 页面手动）
    "organization_generate":   ["project","world","characters"],
    "single_organization_":    ["project","world","characters"],
    "auto_organization_":      ["project","world","characters"],
    # 🔵 角色批量生成（初始化 step3）
    "characters_batch_generation": ["project","world","orgs"],
    "character_generate":      ["project","world","orgs"],
    # 🔵 角色关系生成（初始化 step7）
    "character_relations_generate": ["project"],  # characters_info 已在模板中通过变量注入，不再重复
    # 🔵 大纲生成/续写（初始化 step8 + 页面手动）
    "outline_create":          ["project","world","characters","orgs","past_outlines","foreshadow_ctx"],
    "outline_continue":        ["project","world","characters","orgs","recent","past_outlines","foreshadow_ctx"],
    "outline_expand_":         ["project","world","orgs","outline"],  # characters_info 已在模板中通过变量注入
    # ⚪ 角色职业/组织分配（初始化内部调用 + 页面手动触发）
    "career_assign":           ["project","characters"],
    "org_member_assign":       ["project","characters","orgs"],
    # 🟢 章节生成（页面逐章/批量生成）
    # characters_info 和 chapter_careers 已在模板中通过变量注入，不再重复
    # outline/foreshadow/memory 也在模板中注入，此处仅保留额外 context
    "chapter_generation_":     ["project","world","previous","recent","quality"],
    "chapter_generate_":       ["project","world","previous","recent","quality"],
    # ⚪ 章节后处理（自动摘要/分析）
    "chapter_summary":         ["project","outline"],
    "plot_analysis":           ["project","outline","foreshadow"],
    "volume_summary":          ["project","recent"],
    # 🟢 灵感模式/导入
    "inspire":                 ["project"],
    "inspiration_":            ["project"],
    "book_import_":            ["project"],
    # 🟢 伏笔规划/去AI味/章节重写
    "foreshadow_plan":         ["project","outline","foreshadow"],  # characters_info 已在模板中通过变量注入
    "ai_denoising":            ["project","outline"],
    "chapter_planner":         ["project"],
    "partial_regenerate":      ["project","outline","characters"],
    "chapter_regeneration_":   ["project","outline","characters"],
    # ⚪ 兜底
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


async def _chat_with_tools_json(ai_client, messages, model, temperature, max_tokens, tools, tool_executor) -> dict:
    """带工具调用的 JSON 输出：先用 chat_with_tools 让 AI 按需查询，再解析最终输出为 JSON。
    
    不再退回无工具模式重试——重试会重新发送完整请求浪费大量 token。
    工具调用已提供充足上下文，解析失败说明 AI 输出本身有问题，直接返回错误即可。
    """
    import json as _json
    raw = await ai_client.chat_with_tools(
        messages=messages,
        tools=tools,
        tool_executor=tool_executor,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        max_rounds=5,  # 4轮查询 + 1轮输出，支持多跳查询
    )
    if raw.get("error"):
        return raw
    content = raw.get("content", "")
    # 尝试解析 JSON
    from app.services.json_helper import clean_json_response, parse_json
    try:
        cleaned = clean_json_response(content)
        parsed = parse_json(cleaned)
        if parsed is not None:
            return {"json": parsed, "content": content, "model": raw.get("model", ""),
                    "input_tokens": raw.get("input_tokens", 0),
                    "output_tokens": raw.get("output_tokens", 0),
                    "duration_ms": raw.get("duration_ms", 0)}
    except Exception as e:
        return {"json": None, "error": f"工具调用后JSON解析异常: {e}", "content": content}
    # parse_json 返回 None（非异常），也视为失败
    return {"json": None, "error": "工具调用后无法解析JSON（AI未返回有效JSON结构）", "content": content}


_SKILL_TO_THINKING_MODE = {
    # 世界观生成
    "world_core_generate": "world", "world_detail_generate": "world", "world_generate": "world",
    # 角色生成
    "character_generate": "character", "characters_batch_generation": "character",
    # 大纲
    "outline_create": "outline", "outline_continue": "outline",
    # 剧情展开
    "outline_expand_single": "expand",
    # 章节正文（1-1 / 1-N 首章和续章）
    "chapter_generation_": "chapter",  # 前缀匹配
    # 润色/去AI味
    "ai_denoising": "polish",
    # 剧情分析
    "plot_analysis": "analysis",
}

def _apply_thinking_mode_override(ai_client, skill_name: str, context: dict) -> dict:
    """返回需要覆盖的参数 dict（temperature / reasoning），供 execute_skill 合并。"""
    result = {}
    modes = context.get("_thinking_modes")
    if not modes or not isinstance(modes, dict):
        return result
    mode_key = _SKILL_TO_THINKING_MODE.get(skill_name)
    if not mode_key:
        for prefix, key in _SKILL_TO_THINKING_MODE.items():
            if prefix.endswith("_") and skill_name.startswith(prefix):
                mode_key = key
                break
    if not mode_key or mode_key not in modes:
        return result
    cfg = modes[mode_key]
    if not isinstance(cfg, dict):
        return result
    # enabled=False → 明确关闭推理模式（即使模型默认是推理模型也强制关）
    if not cfg.get("enabled"):
        ai_client.reasoning_model = False
        return result
    # enabled=True → 按用户配置的 effort 设置
    effort = cfg.get("reasoning_effort")
    if effort and effort != "none":
        ai_client.reasoning_effort = effort
        ai_client.reasoning_model = True
    elif effort == "none":
        ai_client.reasoning_model = False
    t = cfg.get("temperature")
    if t is not None:
        result["temperature"] = t / 100 if t > 2 else t
    return result


class SkillEngine:
    """Skill 插件执行引擎"""

    def __init__(self, db: AsyncSession, user_id: int = None):
        self.db = db
        self.user_id = user_id
        self._user_ai_defaults_cache = None

    async def _get_user_ai_defaults(self) -> dict:
        """惰性加载用户 AI 模型配置中的参数默认值。
        仅在 skill 未显式配置时作为 fallback。
        返回值: {"temperature": float|None, "frequency_penalty": float|None, "presence_penalty": float|None, ...}
        """
        if self._user_ai_defaults_cache is not None:
            return self._user_ai_defaults_cache
        self._user_ai_defaults_cache = {}
        if not self.user_id:
            return self._user_ai_defaults_cache
        try:
            from app.models.ai_model import AIModelConfig
            result = await self.db.execute(
                select(AIModelConfig).where(
                    AIModelConfig.user_id == self.user_id,
                    AIModelConfig.is_default == True,
                )
            )
            cfg = result.scalar_one_or_none()
            if cfg:
                # temperature: 存储为 *100, >2 时视为百分制
                t = cfg.temperature
                if t is not None:
                    self._user_ai_defaults_cache["temperature"] = t / 100 if t > 2 else t
                # top_p: 存储为 *100
                if cfg.top_p is not None:
                    self._user_ai_defaults_cache["top_p"] = cfg.top_p / 100
                # frequency_penalty: 存储为 *100, |v|>2 时视为百分制
                if cfg.frequency_penalty is not None:
                    fp = cfg.frequency_penalty
                    self._user_ai_defaults_cache["frequency_penalty"] = fp / 100 if abs(fp) > 2 else fp
                if cfg.presence_penalty is not None:
                    pp = cfg.presence_penalty
                    self._user_ai_defaults_cache["presence_penalty"] = pp / 100 if abs(pp) > 2 else pp
        except Exception:
            pass
        return self._user_ai_defaults_cache

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

    async def _get_user_include_overrides(self) -> dict:
        """收集用户自定义的共享模块内容（@include 解析时优先于文件）。

        返回 {filename: content} 映射。
        """
        if not self.user_id:
            return {}
        # 查所有 shared 类型的 skill，且用户有自定义 system_prompt
        result = await self.db.execute(
            select(SkillConfig).join(Skill, SkillConfig.skill_id == Skill.id).where(
                SkillConfig.user_id == self.user_id,
                Skill.category == "shared",
                SkillConfig.is_customized == True,
            )
        )
        configs = result.scalars().all()
        overrides = {}
        for cfg in configs:
            custom_prompt = (cfg.config or {}).get("system_prompt", "")
            if not custom_prompt:
                continue
            # 查对应的 skill 名，构造 @include 文件名
            skill = (await self.db.execute(select(Skill).where(Skill.id == cfg.skill_id))).scalar_one_or_none()
            if skill:
                # @include 引用的是 .md 文件名
                fname = skill.name + ".md"
                overrides[fname] = custom_prompt
        return overrides

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

        # 解析 @include 指令（支持提示词复用共享片段，用户自定义共享模块优先于文件）
        if "@include:" in system_prompt:
            user_include_overrides = await self._get_user_include_overrides()
            system_prompt = _resolve_includes(system_prompt, user_overrides=user_include_overrides)

        # 替换提示词中的变量（兼容用户模板中直接写的 {变量}）
        had_user_prompt_var = "{user_prompt}" in system_prompt
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

        # 兜底规范化：防止 DB 中残留旧版双花括号（{{ }} → { }）
        system_prompt = _normalize_braces(system_prompt)

        # 写作风格前置：从 context 提取 style 块，作为第一条 system 消息（角色设定之前）
        # 让 AI 在"理解任务"之前先进入"文风模式"，风格指令的优先级最高
        _style_prefix = ""
        if context.get("writing_style_block"):
            _style_prefix = str(context["writing_style_block"])
            logger.info(f"[skill] 写作风格前置注入成功，长度={len(_style_prefix)}")
        else:
            logger.warning(f"[skill] writing_style_block 为空，写作风格未前置注入。context keys: {list(context.keys())}")

        messages = []
        if _style_prefix:
            messages.append({"role": "system", "content": _style_prefix})
        messages.append({"role": "system", "content": system_prompt})

        # ===== 自动注入上下文（按 skill 类型选择性注入）=====
        all_blocks = _inject_context_blocks(context, skill_name)
        info_blocks = []
        write_blocks = []
        info_markers = ["角色", "世界观", "小说信息", "组织", "伏笔", "大纲", "章节", "前章", "data", "人物", "地点"]
        for m in all_blocks:
            content = m.get("content", "")
            if any(marker in content for marker in info_markers):
                info_blocks.append(m)
            else:
                write_blocks.append(m)
        messages.extend(info_blocks)
        if write_blocks:
            context["_post_tool_messages"] = write_blocks

        # ===== 如果启用工具模式，将写作指导（commercial_design/constraints/output）从 skill prompt 中分拆到 post_tool ====
        if tools and tool_executor and skill and len(messages) > 0:
            sp = messages[0].get("content", "")
            # 查找写作指导标签的起始位置
            for tag_start in ("<commercial_design", "<constraints", "<output>"):
                idx = sp.find(tag_start)
                if idx > 0:
                    # 在 tag 开始前的最后一个完整标签结尾切开
                    split_at = sp.rfind("</", 0, idx)
                    if split_at > 0:
                        split_at = sp.find(">", split_at) + 1  # 跳到闭环标签后
                        pre = sp[:split_at].strip()
                        post = sp[split_at:].strip()
                        if pre and post:
                            messages[0]["content"] = pre
                            post_msgs = context.get("_post_tool_messages") or []
                            post_msgs.insert(0, {"role": "system", "content": post})
                            context["_post_tool_messages"] = post_msgs
                        break  # 只处理第一个匹配的标签

        # 用户指令：如果模板里本来就有 {user_prompt}（已替换进 system 消息），则不重复添加。
        user_text = str(context.get("user_prompt", ""))
        if not had_user_prompt_var:
            messages.append({"role": "user", "content": user_text})

        model = merged_config.get("model")
        temperature = merged_config.get("temperature")
        if temperature is not None:
            temperature = temperature / 100 if temperature > 2 else temperature
        top_p = merged_config.get("top_p")
        if top_p is not None:
            top_p = top_p / 100 if top_p > 1 else top_p
        max_tokens = merged_config.get("max_tokens")
        if max_tokens is not None:
            max_tokens = min(max_tokens, settings.AI_MAX_TOKENS)
        # skill 没配 max_tokens → 留 None，让 ai_client 走模型配置默认值
        frequency_penalty = merged_config.get("frequency_penalty")
        presence_penalty = merged_config.get("presence_penalty")

        # skill 未配置的参数 → 回退到用户的 AI 模型默认值
        if temperature is None or top_p is None or frequency_penalty is None or presence_penalty is None:
            user_defaults = await self._get_user_ai_defaults()
            if temperature is None:
                temperature = user_defaults.get("temperature")
            if top_p is None:
                top_p = user_defaults.get("top_p")
            if frequency_penalty is None:
                frequency_penalty = user_defaults.get("frequency_penalty")
            if presence_penalty is None:
                presence_penalty = user_defaults.get("presence_penalty")

        # 章节正文生成的参数钳制：长文本场景对温度和 penalty 敏感
        # 高温度 + penalty 累积 → 2000字后模型在低概率区域采样 → 退化成英文/乱码
        is_chapter_writing = skill_name.startswith("chapter_generation") or skill_name.startswith("chapter_generate")
        if is_chapter_writing:
            # 温度：上限 0.8（>0.8 长文本容易跑飞）
            if temperature is not None and temperature > 0.8:
                logger.info(f"[skill] 章节生成温度钳制：{temperature} → 0.8")
                temperature = 0.8
            # top_p：下限 0.9（<0.9 会截断太多创意词；=1.0 配合高温度会跑飞）
            if top_p is not None and (top_p > 0.98 or top_p < 0.9):
                logger.info(f"[skill] 章节生成 top_p 钳制：{top_p} → 0.95")
                top_p = 0.95
            # penalty：长文本累积效应强，限制在合理范围
            if frequency_penalty is not None and abs(frequency_penalty) > 0.5:
                logger.info(f"[skill] 章节生成 frequency_penalty 钳制：{frequency_penalty} → 0.3")
                frequency_penalty = 0.3 if frequency_penalty > 0 else -0.3
            if presence_penalty is not None and abs(presence_penalty) > 0.5:
                logger.info(f"[skill] 章节生成 presence_penalty 钳制：{presence_penalty} → 0.3")
                presence_penalty = 0.3 if presence_penalty > 0 else -0.3

        if stream:
            _thinking_override = _apply_thinking_mode_override(ai_client, skill_name, context)
            if _thinking_override.get("temperature") is not None and temperature is None:
                temperature = _thinking_override["temperature"]
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
        # 思考模式覆盖（推理深度 + 温度）
        _thinking_override = _apply_thinking_mode_override(ai_client, skill_name, context)
        if _thinking_override.get("temperature") is not None and temperature is None:
            temperature = _thinking_override["temperature"]
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
                        max_tokens=max_tokens,
                        max_rounds=3,  # 章节生成：2轮查询 + 1轮输出，够用且快
                        post_tool_messages=context.get("_post_tool_messages"),
                    )
                else:
                    result = await ai_client.chat_stream_collect(
                        messages=messages, model=model,
                        temperature=temperature, top_p=top_p,
                        max_tokens=max_tokens,
                        frequency_penalty=frequency_penalty,
                        presence_penalty=presence_penalty,
                    )
                if not result.get("error"):
                    break
                err = result.get("error","")
                if "Connection" in err or "connection" in err or "Timeout" in err:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break
        else:
            # JSON 输出技能：如果有工具，走 chat_with_tools 后解析 JSON
            if tools and tool_executor:
                result = await _chat_with_tools_json(
                    ai_client, messages, model, temperature, max_tokens,
                    tools, tool_executor,
                )
            else:
                result = await ai_client.chat_json_retry(
                    messages=messages, model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
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
