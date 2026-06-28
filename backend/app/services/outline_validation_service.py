"""大纲验证服务：检查大纲中的角色/组织是否已创建，缺失则自动补充。

被 outlines.py 的生成/续写端点和 project_init.py 的初始化管线共用。
缺失角色/组织使用系统公用 skill 生成，确保格式一致、内容饱满。
"""

import logging

from sqlalchemy import func
from sqlalchemy import select as _sel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.character import Character
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.outline import Outline

logger = logging.getLogger(__name__)


def build_world_context(project) -> str:
    """从 Project 对象构建世界观的简要文本。"""
    parts = []
    if project.world_time_period:
        parts.append(f"时间：{project.world_time_period}")
    if project.world_location:
        parts.append(f"地点：{project.world_location}")
    if project.world_atmosphere:
        parts.append(f"氛围：{project.world_atmosphere}")
    if project.world_rules:
        parts.append(f"规则：{project.world_rules}")
    return "\n".join(parts) if parts else "暂无"


async def validate_outline_entities(
    db: AsyncSession,
    project_id: int,
    title: str,
    genre: str,
    world_info: str,
    engine,  # SkillEngine
    ai_client,  # AIClient (用于轻量关联 prompt)
) -> int:
    """验证大纲中涉及的角色和组织是否都已创建，缺失则调用公用 skill 自动补充。

    返回补全的实体数量。
    """
    outlines = (
        (await db.execute(_sel(Outline).where(Outline.project_id == project_id))).scalars().all()
    )
    if not outlines:
        return 0

    # 1. 提取大纲中所有角色名和组织名
    outline_char_names = set()
    outline_org_names = set()
    for o in outlines:
        for field_name in ["characters", "organizations"]:
            items = getattr(o, field_name, None)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        (
                            outline_char_names if field_name == "characters" else outline_org_names
                        ).add(item.strip())
                    elif isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        if field_name == "organizations" or item.get("type") == "organization":
                            outline_org_names.add(name)
                        else:
                            outline_char_names.add(name)
        if o.structure and isinstance(o.structure, dict):
            for c in o.structure.get("characters") or []:
                if isinstance(c, dict) and c.get("type") == "organization":
                    outline_org_names.add(str(c.get("name", "")).strip())
                elif isinstance(c, dict):
                    outline_char_names.add(str(c.get("name", "")).strip())
                elif isinstance(c, str):
                    outline_char_names.add(c.strip())
    outline_char_names.discard("")
    outline_org_names.discard("")

    # 2. 对比现有
    existing_chars = (
        (await db.execute(_sel(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    existing_char_names = {c.name for c in existing_chars}
    existing_orgs = (
        (await db.execute(_sel(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    existing_org_names = {o.name for o in existing_orgs}

    missing_chars = outline_char_names - existing_char_names
    missing_orgs = outline_org_names - existing_org_names
    if not missing_chars and not missing_orgs:
        return 0

    total_added = 0

    # 3. 补充缺失角色（调用公用 characters_batch_generation skill，确保格式一致饱满）
    if missing_chars:
        char_names_str = "、".join(missing_chars)
        result = await engine.execute_skill(
            "characters_batch_generation",
            ai_client,
            {
                "genre": genre or "网文",
                "title": title,
                "synopsis": f"大纲中涉及以下角色：{char_names_str}",
                "count": str(len(missing_chars)),
                "existing_characters": "、".join(existing_char_names)
                if existing_char_names
                else "暂无",
                "world_info": world_info,
                "user_prompt": (
                    f"请为小说生成以下角色（已在大纲中出现但尚未创建）：{char_names_str}。\n"
                    f"已有角色：{'、'.join(existing_char_names) if existing_char_names else '暂无'}\n"
                    f"已有组织：{'、'.join(existing_org_names) if existing_org_names else '暂无'}"
                ),
            },
        )
        if not result.get("error"):
            chars_data = result.get("json") or []
            if isinstance(chars_data, dict):
                chars_data = chars_data.get("characters") or chars_data.get("data") or []
            for item in chars_data if isinstance(chars_data, list) else []:
                if isinstance(item, dict) and item.get("name"):
                    db.add(
                        Character(
                            project_id=project_id,
                            name=str(item.get("name", ""))[:100],
                            role=str(item.get("role", "配角"))[:50],
                            gender=str(item.get("gender", ""))[:20],
                            age=str(item.get("age", ""))[:20],
                            identity=str(item.get("identity", ""))[:200],
                            personality=str(item.get("personality", ""))[:2000],
                            background=str(item.get("background", ""))[:2000],
                            ability=str(item.get("ability", ""))[:2000],
                            story_goal=str(item.get("story_goal", ""))[:2000],
                            motivation=str(item.get("motivation", ""))[:2000],
                            weakness=str(item.get("weakness", ""))[:2000],
                            speech_style=str(item.get("speech_style", ""))[:200],
                            arc_type=str(item.get("arc_type", ""))[:200],
                            character_change=str(item.get("character_change", ""))[:2000],
                            growth_experience=str(item.get("growth_experience", ""))[:2000],
                        )
                    )
                    total_added += 1
            await db.commit()

    # 4. 补充缺失组织（调用公用 organization_generate skill）
    if missing_orgs:
        org_names_str = "、".join(missing_orgs)
        result = await engine.execute_skill(
            "organization_generate",
            ai_client,
            {
                "title": title,
                "genre": genre or "网文",
                "synopsis": f"大纲中涉及以下组织：{org_names_str}",
                "world_info": world_info,
                "user_prompt": (
                    f"请为小说生成以下组织（已在大纲中出现但尚未创建）：{org_names_str}。\n"
                    f"已有组织：{'、'.join(existing_org_names) if existing_org_names else '暂无'}\n"
                    f"已有角色：{'、'.join(existing_char_names) if existing_char_names else '暂无'}"
                ),
            },
        )
        if not result.get("error"):
            orgs_data = result.get("json") or []
            if isinstance(orgs_data, dict):
                orgs_data = orgs_data.get("organizations") or orgs_data.get("data") or []
            for item in orgs_data if isinstance(orgs_data, list) else []:
                if isinstance(item, dict) and item.get("name"):
                    pv = item.get("power_value", 50)
                    try:
                        pv = int(pv)
                    except Exception:
                        pv = 50
                    db.add(
                        Organization(
                            project_id=project_id,
                            name=str(item.get("name", ""))[:100],
                            org_type=str(
                                item.get("org_type", str(item.get("organization_type", "")))
                            )[:50],
                            description=str(item.get("description", ""))[:2000],
                            power_value=pv,
                            location=str(item.get("location", ""))[:200],
                            motto=str(item.get("motto", ""))[:200],
                            color=str(item.get("color", ""))[:20],
                        )
                    )
                    total_added += 1
            await db.commit()

    # 5. 重新关联角色-组织
    if missing_chars or missing_orgs:
        chars = (
            (await db.execute(_sel(Character).where(Character.project_id == project_id)))
            .scalars()
            .all()
        )
        orgs = (
            (await db.execute(_sel(Organization).where(Organization.project_id == project_id)))
            .scalars()
            .all()
        )
        if chars and orgs:
            unassigned = []
            for c in chars:
                existing = await db.scalar(
                    _sel(func.count(OrganizationMember.id)).where(
                        OrganizationMember.character_id == c.id
                    )
                )
                if not existing:
                    unassigned.append(c)
            if unassigned:
                org_list = "\n".join(
                    f"- ID:{o.id} {o.name}（{o.org_type or '势力'}，势力值:{o.power_value or 50}）"
                    for o in orgs[:10]
                )
                char_list = "\n".join(
                    f"- ID:{c.id} {c.name}（{c.role or '角色'}，{(c.personality or '')[:80]}，职业:{c.main_career_stage_desc or '无'}）"
                    for c in unassigned[:20]
                )
                r = await engine.execute_skill(
                    "org_member_assign",
                    ai_client,
                    {
                        "title": title,
                        "genre": genre or "网文",
                        "user_prompt": f"""已有组织：\n{org_list}\n\n待分配角色：\n{char_list}""",
                    },
                )
                if not r.get("error"):
                    data = r.get("json") or []
                    if isinstance(data, dict):
                        data = data.get("assignments") or data.get("data") or []
                    char_ids = {c.id for c in unassigned}
                    org_ids = {o.id for o in orgs}
                    for a in data if isinstance(data, list) else []:
                        if not isinstance(a, dict):
                            continue
                        cid = a.get("character_id")
                        oid = a.get("organization_id")
                        if cid not in char_ids or (oid and oid not in org_ids):
                            continue
                        char = next((c for c in chars if c.id == cid), None)
                        if char and oid and not char.organization_id:
                            char.organization_id = oid
                            db.add(
                                OrganizationMember(
                                    organization_id=oid,
                                    character_id=cid,
                                    role=str(a.get("role", "成员"))[:50],
                                    status="active",
                                    source="ai",
                                )
                            )
                    await db.commit()

    return total_added
