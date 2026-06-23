"""内置 Skill 管理。

提示词模板存储在 prompts/ 目录下的独立 JSON 文件中。
启动时由 init_builtin_skills() 加载到 Skill 表。
用户在「提示词」页面自定义的版本优先级最高，不会被覆盖。
"""
import json
import os
import logging
from typing import List, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.skill import Skill

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
            if data.get("name") and data.get("system_prompt"):
                skills.append(data)
            else:
                logger.warning(f"[builtin] 跳过无效模板: {filename}（缺少 name 或 system_prompt）")
        except Exception as e:
            logger.error(f"[builtin] 加载模板失败: {filename} - {e}")

    return skills


# 启动时加载一次（模块级缓存）
BUILTIN_SKILLS = load_builtin_skills()


async def init_builtin_skills(db: AsyncSession):
    """初始化内置 Skill（统一入口，prompts/ 目录是唯一真相源）。

    逻辑：
    - 新 skill：从 JSON 文件创建
    - 已有 skill：检查 PromptTemplate 激活版本
      - 如果用户通过「提示词」页面激活了自定义版本 → 保留，不覆盖
      - 如果没有用户自定义 → 从 JSON 文件更新
    """
    from app.models.prompt_template import PromptTemplate, PromptVersion

    for skill_data in BUILTIN_SKILLS:
        result = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
        existing = result.scalar_one_or_none()

        if not existing:
            # 新 skill：直接创建
            skill = Skill(**skill_data)
            db.add(skill)
        else:
            # 已有 skill：检查是否有用户通过 PromptTemplate 激活的自定义版本
            pt_name = skill_data["name"].upper()
            pt_result = await db.execute(
                select(PromptTemplate).where(PromptTemplate.name == pt_name)
            )
            pt_obj = pt_result.scalar_one_or_none()
            user_customized = False
            if pt_obj and pt_obj.current_version_id:
                ver_result = await db.execute(
                    select(PromptVersion).where(PromptVersion.id == pt_obj.current_version_id)
                )
                active_ver = ver_result.scalar_one_or_none()
                # 如果激活版本的 prompt 与当前 DB skill 一致，说明是用户主动激活的
                if active_ver and active_ver.system_prompt == existing.system_prompt:
                    user_customized = True

            if not user_customized:
                # 没有用户自定义 → 从 JSON 文件更新
                existing.system_prompt = skill_data["system_prompt"]
                existing.parameters = skill_data.get("parameters", {})

    await db.commit()
    logger.info(f"[builtin] 提示词模板已就绪（{len(BUILTIN_SKILLS)} 个模板）")
