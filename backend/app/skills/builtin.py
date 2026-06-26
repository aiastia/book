"""内置 Skill 管理。

提示词模板存储在 prompts/ 目录下的独立 JSON 文件中。
启动时由 init_builtin_skills() 加载到 Skill 表。
用户在「提示词」页面自定义的版本优先级最高，不会被覆盖。
提供 force=True 模式一键清除所有用户自定义。
"""
import json
import os
import logging
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.skill import Skill, SkillConfig

logger = logging.getLogger(__name__)

# prompts 目录路径
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_builtin_skills() -> List[Dict]:
    """从 prompts/ 目录加载所有 JSON 模板文件。"""
    skills = []
    if not os.path.isdir(PROMPTS_DIR):
        logger.warning(f"[builtin] prompts 目录不存在: {PROMPTS_DIR}")
        return skills

    for filename in sorted(os.listdir(PROMPTS_DIR)):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(PROMPTS_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 支持 system_prompt_file：从外部 .md 文件加载提示词
            sp_file = data.pop("system_prompt_file", None)
            if sp_file:
                md_path = os.path.join(PROMPTS_DIR, sp_file)
                with open(md_path, "r", encoding="utf-8") as mf:
                    data["system_prompt"] = mf.read().strip()
            # 规范化：模板中的 {{ }} 是 JSON 示例的转义写法，实际应发送 { }
            # 否则 AI 看到 {{ }} 可能照抄双花括号，导致 JSON 解析失败
            if data.get("system_prompt"):
                data["system_prompt"] = _normalize_braces(data["system_prompt"])
            if data.get("name") and data.get("system_prompt"):
                skills.append(data)
            else:
                logger.warning(f"[builtin] 跳过无效模板: {filename}（缺少 name 或 system_prompt）")
        except Exception as e:
            logger.error(f"[builtin] 加载模板失败: {filename} - {e}")

    return skills


def _normalize_braces(text: str) -> str:
    """将模板中的双花括号 {{ }} 规范化为单花括号 { }。

    模板文件用 {{ }} 表示 JSON 示例（如 {{"key": "value"}}），
    但实际发送给 AI 时应为单花括号。双花括号会让 AI 模仿返回
    无效的 {{...}} JSON，导致解析失败。
    
    只在 JSON 格式示例场景下替换：连续的 {{ 或 }}。
    """
    if not text:
        return text
    # 只替换连续的两个花括号（{{ → { ， }} → }）
    # 不替换单个花括号（那是变量占位符 {var}）
    text = text.replace("{{", "{").replace("}}", "}")
    return text


# 启动时加载一次（模块级缓存）
BUILTIN_SKILLS = load_builtin_skills()


async def init_builtin_skills(db: AsyncSession, force: bool = False):
    """初始化内置 Skill（prompts/ 目录是唯一真相源）。

    force=False（默认）：智能更新
      - 新 skill → 创建
      - 已有 skill + 用户未真正修改 → 用文件内容覆盖
      - 已有 skill + 用户真正修改过 → 保留用户版本

    force=True：一键清除所有用户自定义，文件内容强制覆盖
      - 清除所有 SkillConfig（用户级覆盖）
      - 所有 Skill 的 system_prompt 用文件内容覆盖
    """
    from app.models.prompt_template import PromptTemplate, PromptVersion

    for skill_data in BUILTIN_SKILLS:
        result = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
        existing = result.scalar_one_or_none()

        if not existing:
            skill = Skill(**skill_data)
            db.add(skill)
            continue

        if force:
            # 强制覆盖模式
            existing.system_prompt = skill_data["system_prompt"]
            existing.parameters = skill_data.get("parameters", {})
            existing.config = skill_data.get("config", {})
            existing.category = skill_data.get("category", existing.category)
            existing.display_name = skill_data.get("display_name", existing.display_name)
            existing.description = skill_data.get("description", existing.description)
            existing.skill_type = skill_data.get("skill_type", existing.skill_type)
            existing.is_enabled = skill_data.get("is_enabled", True)
            # 清除所有用户的 SkillConfig 覆盖
            configs = (await db.execute(
                select(SkillConfig).where(SkillConfig.skill_id == existing.id)
            )).scalars().all()
            for sc in configs:
                await db.delete(sc)
            if configs:
                logger.info(f"[builtin] 强制覆盖 {skill_data['name']}，清除 {len(configs)} 个用户配置")
            continue

        # 智能模式：判断用户是否真正自定义了
        # 直接看 SkillConfig.is_customized（用户自定义的真实标志），
        # 而非比较 PromptVersion vs Skill（两个表容易不一致，判断脆弱）
        user_configs = (await db.execute(
            select(SkillConfig).where(SkillConfig.skill_id == existing.id)
        )).scalars().all()
        user_customized = any(sc.is_customized for sc in user_configs)

        if not user_customized:
            old_prompt = existing.system_prompt
            existing.system_prompt = skill_data["system_prompt"]
            existing.parameters = skill_data.get("parameters", {})
            existing.config = skill_data.get("config", {})
            logger.info(f"[builtin] 更新内置模板: {skill_data['name']}")

            # 清理 SkillConfig 中恰好等于旧版本的副本
            all_configs = (await db.execute(
                select(SkillConfig).where(SkillConfig.skill_id == existing.id)
            )).scalars().all()
            for sc in all_configs:
                if (sc.config or {}).get("system_prompt") == old_prompt:
                    sc.config = {k: v for k, v in (sc.config or {}).items() if k != "system_prompt"}
                    logger.info(f"[builtin] 清除用户 {sc.user_id} 对 {skill_data['name']} 的旧版本副本")

    # 清理孤儿 Skill：文件已删除但 DB 残留的
    builtin_names = {s["name"] for s in BUILTIN_SKILLS}
    all_builtins = (await db.execute(
        select(Skill).where(Skill.skill_type == "builtin")
    )).scalars().all()
    orphans = [s for s in all_builtins if s.name not in builtin_names]
    for s in orphans:
        # 先删关联的用户配置
        configs = (await db.execute(select(SkillConfig).where(SkillConfig.skill_id == s.id))).scalars().all()
        for sc in configs:
            await db.delete(sc)
        await db.delete(s)
    if orphans:
        logger.info(f"[builtin] 清理 {len(orphans)} 个孤儿 Skill: {[s.name for s in orphans]}")

    await db.commit()
    logger.info(f"[builtin] 提示词模板已就绪（{len(BUILTIN_SKILLS)} 个模板）{' [强制模式]' if force else ''}")


async def force_reset_all_skills(db: AsyncSession):
    """一键重置：清除所有用户自定义，用文件内容覆盖所有提示词。

    可在管理页面或命令行调用。
    """
    # 1. 清除所有 SkillConfig
    result = await db.execute(select(SkillConfig))
    all_configs = result.scalars().all()
    for sc in all_configs:
        await db.delete(sc)
    logger.info(f"[builtin] 清除 {len(all_configs)} 条用户配置")

    # 2. 重置所有 PromptTemplate 的 current_version
    from app.models.prompt_template import PromptTemplate, PromptVersion
    pts = (await db.execute(select(PromptTemplate))).scalars().all()
    for pt in pts:
        pt.current_version_id = None
    logger.info(f"[builtin] 重置 {len(pts)} 个 PromptTemplate")

    # 3. 删除所有 PromptVersion（重新同步）
    versions = (await db.execute(select(PromptVersion))).scalars().all()
    for v in versions:
        await db.delete(v)
    logger.info(f"[builtin] 删除 {len(versions)} 条 PromptVersion")

    await db.commit()

    # 4. 强制重新加载内置 skills
    await init_builtin_skills(db, force=True)
    logger.info("[builtin] 全部提示词已重置为系统默认")
