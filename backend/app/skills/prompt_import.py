"""从 prompt-templates JSON 文件批量导入提示词到 Skill 表"""
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.skill import Skill
from app.models.prompt_template import PromptTemplate, PromptVersion

# 模板 key 到 Skill category 的映射
CATEGORY_MAP = {
    "world": "world",
    "character": "character",
    "outline": "outline",
    "chapter": "chapter",
    "analysis": "analysis",
    "foreshadow": "foreshadow",
    "inspire": "inspire",
    "skill": "skill",
    "mcp": "mcp",
    "import": "import",
    "tool": "tool",
}


def _guess_category(key: str) -> str:
    """根据 template_key 前缀推断 category"""
    if key.startswith("SKILL_STORY_"):
        return "skill"
    if key.startswith("MCP_"):
        return "mcp"
    if key.startswith("INSPIRATION_"):
        return "inspire"
    if key.startswith("BOOK_IMPORT_"):
        return "import"
    if key.startswith("CHAPTER_"):
        return "chapter"
    if key.startswith("OUTLINE_"):
        return "outline"
    if key.startswith("WORLD_"):
        return "world"
    if key.startswith("AUTO_CHARACTER") or key.startswith("CHARACTERS_") or key.startswith("SINGLE_CHARACTER"):
        return "character"
    if key.startswith("AUTO_ORGANIZATION") or key.startswith("SINGLE_ORGANIZATION") or key.startswith("CAREER"):
        return "world"
    if key.startswith("PLOT_"):
        return "analysis"
    if key in ("AI_DENOISING", "PARTIAL_REGENERATE", "NOVEL_COVER_PROMPT_TEMPLATE", "CHAPTER_REGENERATION_SYSTEM"):
        return "tool"
    return "other"


def load_templates_from_json(json_path: str) -> list[dict]:
    """从 JSON 文件读取提示词模板列表"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("templates", [])


def template_to_skill_data(tpl: dict) -> dict:
    """将单个 JSON 模板转换为 Skill 数据字典"""
    key = tpl["template_key"]
    name = tpl["template_key"].lower()
    display_name = tpl.get("template_name", key)
    content = tpl.get("template_content", "")

    # 某些模板有 system_prompt 和 user_prompt 区分（如灵感系列）
    is_system = "_SYSTEM" in key

    return {
        "name": name,
        "display_name": display_name,
        "description": tpl.get("template_description", display_name),
        "category": _guess_category(key),
        "skill_type": "builtin",
        "system_prompt": content,
        "parameters": tpl.get("template_variables") or {},
        "is_enabled": True,
    }


async def import_prompt_templates(db: AsyncSession, json_path: str = None):
    """批量导入提示词模板到 Skill 表（幂等：同名跳过）"""
    if json_path is None:
        # 默认路径：项目根目录下的 prompt-templates 文件
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        json_path = os.path.join(base_dir, "prompt-templates-2026-06-05.json")

    if not os.path.exists(json_path):
        return 0

    templates = load_templates_from_json(json_path)
    imported = 0

    for tpl in templates:
        skill_data = template_to_skill_data(tpl)
        # 检查是否已存在
        result = await db.execute(select(Skill).where(Skill.name == skill_data["name"]))
        existing = result.scalar_one_or_none()
        if existing:
            # 更新已有记录的提示词内容（保留用户自定义的开关状态）
            existing.display_name = skill_data["display_name"]
            existing.description = skill_data["description"]
            existing.category = skill_data["category"]
            existing.system_prompt = skill_data["system_prompt"]
            existing.parameters = skill_data["parameters"]
        else:
            skill = Skill(**skill_data)
            db.add(skill)
        imported += 1

    await db.commit()
    return imported


async def import_to_prompt_templates(db: AsyncSession, json_path: str = None):
    """批量导入提示词模板到 PromptTemplate + PromptVersion 表（幂等：同名更新内容）"""
    if json_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        json_path = os.path.join(base_dir, "prompt-templates-2026-06-05.json")

    if not os.path.exists(json_path):
        return 0

    templates = load_templates_from_json(json_path)
    imported = 0

    for tpl in templates:
        key = tpl.get("template_key", "")
        if not key:
            continue
        name = key
        category = _guess_category(key)
        description = tpl.get("template_description", "") or tpl.get("template_name", "")
        system_prompt = tpl.get("template_content", "")

        # 解析 variables（JSON 字符串或列表）
        variables = tpl.get("parameters") or tpl.get("template_variables") or []
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                variables = []

        # 检查是否已存在同名模板
        result = await db.execute(select(PromptTemplate).where(PromptTemplate.name == name))
        existing = result.scalar_one_or_none()

        if existing:
            # 更新模板元信息
            existing.description = description
            existing.category = category
            # 更新当前激活版本的内容
            if existing.current_version_id:
                ver_result = await db.execute(
                    select(PromptVersion).where(PromptVersion.id == existing.current_version_id)
                )
                active_ver = ver_result.scalar_one_or_none()
                if active_ver:
                    active_ver.system_prompt = system_prompt
                    active_ver.variables = variables
        else:
            template = PromptTemplate(
                name=name,
                category=category,
                description=description,
                is_system=True,
            )
            db.add(template)
            await db.flush()

            version = PromptVersion(
                template_id=template.id,
                version=1,
                system_prompt=system_prompt,
                user_prompt="",
                variables=variables,
                config={},
                is_active=True,
            )
            db.add(version)
            await db.flush()

            template.current_version_id = version.id

        imported += 1

    await db.commit()
    return imported
