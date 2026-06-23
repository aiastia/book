"""Skill 提示词覆盖工具。

builtin.py 是唯一的提示词来源（含从 JSON 迁移的模板）。
此模块提供 _force_builtin_override()，在启动时用 builtin 正确版本
覆盖数据库中变量名错误的旧模板。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.skill import Skill
from app.skills.builtin import BUILTIN_SKILLS


# 这些 JSON 模板的变量名与路由传参不匹配，会导致提示词中残留 {变量} 占位符。
# 已在 builtin.py 中提供了修正版本，启动时强制覆盖。
SKIP_OVERWRITE_KEYS = {
    "CHARACTERS_BATCH_GENERATION",
    "SINGLE_CHARACTER_GENERATION",
    "AUTO_CHARACTER_GENERATION",
    "AUTO_CHARACTER_ANALYSIS",
    "CAREER_SYSTEM_GENERATION",
}


async def _force_builtin_override(db: AsyncSession):
    """每次启动时用 builtin.py 的正确版本覆盖 DB 中变量名错误的 skill。

    仅覆盖 system_prompt 和 parameters，保留 is_enabled 等用户配置。
    """
    # 映射 JSON key → builtin skill name
    name_map = {
        "characters_batch_generation": "characters_batch_generation",
        "single_character_generation": "character_generate",
        "auto_character_generation": None,
        "auto_character_analysis": None,
        "career_system_generation": "career_system_generation",
    }
    builtin_by_name = {s["name"]: s for s in BUILTIN_SKILLS}
    for json_name in SKIP_OVERWRITE_KEYS:
        builtin_name = name_map.get(json_name.lower())
        if not builtin_name or builtin_name not in builtin_by_name:
            continue
        bs = builtin_by_name[builtin_name]
        result = await db.execute(select(Skill).where(Skill.name == json_name.lower()))
        existing = result.scalar_one_or_none()
        if existing:
            existing.system_prompt = bs["system_prompt"]
            existing.parameters = bs.get("parameters", {})
    await db.commit()
