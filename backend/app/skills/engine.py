import asyncio
"""Skill 执行引擎"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.skill import Skill, SkillConfig
from app.core.ai_client import AIClient


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

        # Fallback：尝试变体名匹配
        # chapter_generate_one_to_one <-> chapter_generation_one_to_one
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
            return {"is_enabled": cfg.is_enabled, "config": cfg.config}
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

        # 检查用户级配置覆盖
        user_cfg = await self.get_user_config(skill.id)
        if user_cfg and not user_cfg["is_enabled"]:
            return {"error": f"Skill '{skill_name}' 已被用户禁用"}

        # 合并 Skill 配置
        merged_config = {**skill.config}
        if user_cfg and user_cfg.get("config"):
            merged_config.update(user_cfg["config"])

        # 构建消息
        system_prompt = skill.system_prompt
        if user_cfg and user_cfg.get("config", {}).get("system_prompt"):
            system_prompt = user_cfg["config"]["system_prompt"]

        # 替换提示词中的变量
        for key, value in context.items():
            if isinstance(value, str):
                system_prompt = system_prompt.replace(f"{{{key}}}", value)
        # 别名兼容：自定义 prompt 可能用简短变量名（如 {content} 而非 {chapter_content}）
        _aliases = {
            "content": context.get("chapter_content", context.get("content", "")),
            "title": context.get("chapter_title", context.get("title", "")),
        }
        for key, value in _aliases.items():
            if isinstance(value, str) and f"{{{key}}}" in system_prompt:
                system_prompt = system_prompt.replace(f"{{{key}}}", value)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context.get("user_prompt", "")},
        ]

        # 获取模型参数
        model = merged_config.get("model")
        temperature = merged_config.get("temperature")
        if temperature is not None:
            temperature = temperature / 100 if temperature > 2 else temperature
        top_p = merged_config.get("top_p")
        if top_p is not None:
            top_p = top_p / 100 if top_p > 1 else top_p
        max_tokens = merged_config.get("max_tokens")

        # 执行 pre_hooks
        for hook in (skill.pre_hooks or []):
            hook_type = hook.get("type")
            if hook_type == "inject_context":
                # 注入额外上下文
                inject_key = hook.get("config", {}).get("key")
                if inject_key and inject_key in context:
                    messages.insert(1, {
                        "role": "system",
                        "content": f"参考信息：\n{context[inject_key]}"
                    })

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

        # 调用 AI
        # 章节生成类 skill 返回纯文本正文（不是 JSON），用普通 chat
        is_text_output = skill_name.startswith("chapter_generation") or skill_name == "ai_denoising"
        if is_text_output:
            # 纯文本输出（章节正文），带连接错误重试
            result = None
            for attempt in range(3):
                # 如果有工具，走 chat_with_tools（AI 可按需查询角色/伏笔/物品等）
                if tools and tool_executor:
                    result = await ai_client.chat_with_tools(
                        messages=messages,
                        tools=tools,
                        tool_executor=tool_executor,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens or 16384,
                    )
                else:
                    result = await ai_client.chat(
                        messages=messages, model=model,
                        temperature=temperature, top_p=top_p,
                        max_tokens=max_tokens or 16384,
                    )
                if not result.get("error"):
                    break
                err = result.get("error","")
                if "Connection" in err or "connection" in err or "Timeout" in err:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break
        else:
            # 其他 skill 返回 JSON，用带重试的 chat_json_retry
            result = await ai_client.chat_json_retry(
                messages=messages, model=model,
                temperature=temperature,
                max_tokens=max_tokens or 16384,
            )

        # 执行 post_hooks
        for hook in (skill.post_hooks or []):
            hook_type = hook.get("type")
            if hook_type == "parse_json" and result.get("content"):
                pass  # chat_json 已处理

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