"""大纲验证服务：检查大纲中的角色/组织是否已创建，缺失则自动补充。

被 outlines.py 的生成/续写端点和 project_init.py 的初始化管线共用。
"""
import logging
from sqlalchemy import func, select as _sel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.ai_client import AIClient
from app.models.outline import Outline
from app.models.character import Character
from app.models.organization import Organization, OrganizationMember

logger = logging.getLogger(__name__)


def build_world_context(project) -> str:
    """从 Project 对象构建世界观的简要文本。"""
    parts = []
    if project.world_time_period: parts.append(f"时间：{project.world_time_period}")
    if project.world_location: parts.append(f"地点：{project.world_location}")
    if project.world_atmosphere: parts.append(f"氛围：{project.world_atmosphere}")
    if project.world_rules: parts.append(f"规则：{project.world_rules}")
    return "\n".join(parts) if parts else "暂无"


async def validate_outline_entities(
    db: AsyncSession,
    project_id: int,
    title: str,
    genre: str,
    world_info: str,
    ai_client: AIClient,
) -> int:
    """验证大纲中涉及的角色和组织是否都已创建，缺失则自动补充。

    返回补全的实体数量。
    """
    outlines = (await db.execute(
        _sel(Outline).where(Outline.project_id == project_id)
    )).scalars().all()
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
                        (outline_char_names if field_name == "characters" else outline_org_names).add(item.strip())
                    elif isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        if field_name == "organizations" or item.get("type") == "organization":
                            outline_org_names.add(name)
                        else:
                            outline_char_names.add(name)
        # 检查 structure 中的 characters 数组（用户自定义模板格式）
        if o.structure and isinstance(o.structure, dict):
            for c in (o.structure.get("characters") or []):
                if isinstance(c, dict) and c.get("type") == "organization":
                    outline_org_names.add(str(c.get("name", "")).strip())
                elif isinstance(c, dict):
                    outline_char_names.add(str(c.get("name", "")).strip())
                elif isinstance(c, str):
                    outline_char_names.add(c.strip())
    outline_char_names.discard("")
    outline_org_names.discard("")

    # 2. 对比现有
    existing_chars = (await db.execute(_sel(Character).where(Character.project_id == project_id))).scalars().all()
    existing_char_names = {c.name for c in existing_chars}
    existing_orgs = (await db.execute(_sel(Organization).where(Organization.project_id == project_id))).scalars().all()
    existing_org_names = {o.name for o in existing_orgs}

    missing_chars = outline_char_names - existing_char_names
    missing_orgs = outline_org_names - existing_org_names
    if not missing_chars and not missing_orgs:
        return 0

    total_added = 0

    # 3. 补充缺失角色
    if missing_chars:
        char_list = "\n".join(missing_chars)
        result = await ai_client.chat_json_retry(messages=[{"role": "user", "content": f"""为小说《{title}》（题材：{genre or '网文'}）创建以下角色。这些角色出现在大纲中但尚未创建。

需创建的角色：{char_list}
世界观：{world_info}
已有角色：{'、'.join(existing_char_names) or '暂无'}
已有组织：{'、'.join(existing_org_names) or '暂无'}

要求：每个角色包含 name、role（配角）、gender、age、identity、personality、background、occupation、story_goal、motivation、ability。返回纯JSON数组。"""}], temperature=0.8, max_tokens=4096)
        if not result.get("error"):
            chars_data = result.get("json") or []
            if isinstance(chars_data, dict):
                chars_data = chars_data.get("characters") or chars_data.get("data") or []
            for item in (chars_data if isinstance(chars_data, list) else []):
                if isinstance(item, dict) and item.get("name"):
                    db.add(Character(
                        project_id=project_id,
                        name=str(item.get("name", ""))[:100], role=str(item.get("role", "配角"))[:50],
                        gender=str(item.get("gender", ""))[:20], age=str(item.get("age", ""))[:20],
                        identity=str(item.get("identity", ""))[:200],
                        personality=str(item.get("personality", ""))[:2000],
                        background=str(item.get("background", ""))[:2000],
                        occupation=str(item.get("occupation", ""))[:200],
                        ability=str(item.get("ability", ""))[:2000],
                        story_goal=str(item.get("story_goal", ""))[:2000],
                        motivation=str(item.get("motivation", ""))[:2000],
                    ))
                    total_added += 1
            await db.commit()

    # 4. 补充缺失组织
    if missing_orgs:
        org_list = "\n".join(missing_orgs)
        result = await ai_client.chat_json_retry(messages=[{"role": "user", "content": f"""为小说《{title}》（题材：{genre or '网文'}）创建以下组织。这些组织出现在大纲中但尚未创建。

需创建的组织：{org_list}
世界观：{world_info}
已有组织：{'、'.join(existing_org_names) or '暂无'}
已有角色：{'、'.join(existing_char_names) or '暂无'}

要求：每个组织包含 name、org_type、description（100-200字）、power_value（0-100）。返回纯JSON数组。"""}], temperature=0.8, max_tokens=4096)
        if not result.get("error"):
            orgs_data = result.get("json") or []
            if isinstance(orgs_data, dict):
                orgs_data = orgs_data.get("organizations") or orgs_data.get("data") or []
            for item in (orgs_data if isinstance(orgs_data, list) else []):
                if isinstance(item, dict) and item.get("name"):
                    pv = item.get("power_value", 50)
                    try: pv = int(pv)
                    except: pv = 50
                    db.add(Organization(project_id=project_id,
                        name=str(item.get("name", ""))[:100], org_type=str(item.get("org_type", ""))[:50],
                        description=str(item.get("description", ""))[:2000], power_value=pv))
                    total_added += 1
            await db.commit()

    # 5. 重新关联角色-组织
    if missing_chars or missing_orgs:
        chars = (await db.execute(_sel(Character).where(Character.project_id == project_id))).scalars().all()
        orgs = (await db.execute(_sel(Organization).where(Organization.project_id == project_id))).scalars().all()
        if chars and orgs:
            unassigned = []
            for c in chars:
                existing = await db.scalar(_sel(func.count(OrganizationMember.id)).where(
                    OrganizationMember.character_id == c.id
                ))
                if not existing:
                    unassigned.append(c)
            if unassigned:
                org_list = "\n".join(f"- ID:{o.id} {o.name}（{o.org_type or '势力'}，势力值:{o.power_value or 50}）" for o in orgs[:10])
                char_list = "\n".join(
                    f"- ID:{c.id} {c.name}（{c.role or '角色'}，{(c.personality or '')[:80]}，职业:{c.occupation or '无'}）"
                    for c in unassigned[:20]
                )
                r = await ai_client.chat_json_retry(messages=[{"role": "user", "content": f"""将以下角色分配到最合适的组织。返回纯JSON数组。

已有组织：\n{org_list}
待分配角色：\n{char_list}

返回：[{{"character_id":0,"organization_id":0,"role":"成员"}}]"""}], temperature=0.7, max_tokens=2048)
                if not r.get("error"):
                    data = r.get("json") or []
                    if isinstance(data, dict): data = data.get("assignments") or data.get("data") or []
                    char_ids = {c.id for c in unassigned}; org_ids = {o.id for o in orgs}
                    for a in (data if isinstance(data, list) else []):
                        if not isinstance(a, dict): continue
                        cid = a.get("character_id"); oid = a.get("organization_id")
                        if cid not in char_ids or (oid and oid not in org_ids): continue
                        char = next((c for c in chars if c.id == cid), None)
                        if char and oid and not char.organization_id:
                            char.organization_id = oid
                            db.add(OrganizationMember(organization_id=oid, character_id=cid, role=str(a.get("role", "成员"))[:50], status="active", source="ai"))
                    await db.commit()

    return total_added
