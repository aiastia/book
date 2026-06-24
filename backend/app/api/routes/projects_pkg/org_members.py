"""组织成员管理 + 组织树（#18 增强）。

在 worlds.py 现有组织 CRUD 基础上，补充：
- 成员管理（职位/忠诚度/贡献度 CRUD）
- 组织树查询（parent_org_id 层级）
- 组织详情增强（含成员数/势力值）
"""
import logging
from app.api.routes.projects_pkg.base import *
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.character import Character

logger = logging.getLogger(__name__)
router = make_router()


class MemberCreateReq(BaseModel):
    character_id: int
    position: str = ""
    rank: int = 0
    status: str = "active"
    loyalty: int = 50
    contribution: int = 0
    joined_at: str = ""
    notes: str = ""


@router.get("/{project_id}/organizations/tree")
async def org_tree(
    project_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """组织树形结构（带 children 嵌套 + 成员数）。"""
    await get_user_project(db, project_id, user)
    orgs = (await db.execute(
        select(Organization).where(Organization.project_id == project_id)
        .order_by(Organization.tree_level.asc(), Organization.id.asc())
    )).scalars().all()
    # 统计每个组织的成员数
    member_counts = {}
    if orgs:
        from sqlalchemy import func
        rows = (await db.execute(
            select(OrganizationMember.organization_id, func.count(OrganizationMember.id))
            .where(OrganizationMember.project_id == project_id, OrganizationMember.status == "active")
            .group_by(OrganizationMember.organization_id)
        )).all()
        member_counts = {r[0]: r[1] for r in rows}

    by_id = {}
    for o in orgs:
        d = {
            "id": o.id, "name": o.name, "org_type": o.org_type or "",
            "description": o.description or "",
            "power_value": o.power_value if o.power_value is not None else 50,
            "power_level": o.power_level or "",
            "tree_level": o.tree_level or 0,
            "parent_org_id": o.parent_org_id,
            "location": o.location or "",
            "motto": o.motto or "",
            "color": o.color or "",
            "status": o.status or "active",
            "member_count": member_counts.get(o.id, 0),
            "children": [],
        }
        by_id[o.id] = d
    roots = []
    for o in orgs:
        node = by_id[o.id]
        if o.parent_org_id and o.parent_org_id in by_id:
            by_id[o.parent_org_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.put("/{project_id}/organizations/{org_id}/tree")
async def update_org_tree(
    project_id: int, org_id: int, req: dict,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """更新组织的层级关系（父组织/层级/势力值等）。"""
    org = (await db.execute(
        select(Organization).where(Organization.id == org_id, Organization.project_id == project_id)
    )).scalar_one_or_none()
    if not org:
        raise HTTPException(404, "组织不存在")
    if "parent_org_id" in req:
        new_parent = req["parent_org_id"]
        # 防止自引用 / 循环
        if new_parent == org_id:
            raise HTTPException(400, "不能将自身设为父组织")
        org.parent_org_id = new_parent or None
        # 重算层级
        if new_parent:
            parent = (await db.execute(select(Organization).where(Organization.id == new_parent))).scalar_one_or_none()
            org.tree_level = (parent.tree_level + 1) if parent else 0
        else:
            org.tree_level = 0
    for k in ["power_value", "location", "motto", "color", "status", "org_type", "description"]:
        if k in req:
            setattr(org, k, req[k])
    await db.commit()
    return {"ok": True}


# ============ 组织成员 ============
@router.get("/{project_id}/organizations/{org_id}/members")
async def list_members(
    project_id: int, org_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """列出组织成员（含角色名）。角色↔组织关系已统一到 OrganizationMember 表。"""
    await get_user_project(db, project_id, user)
    members = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.project_id == project_id,
        ).order_by(OrganizationMember.rank.desc())
    )).scalars().all()
    char_ids = [m.character_id for m in members]
    char_map = {}
    if char_ids:
        chars = (await db.execute(select(Character).where(Character.id.in_(char_ids)))).scalars().all()
        char_map = {c.id: c.name for c in chars}
    return [{**m.to_dict(), "character_name": char_map.get(m.character_id, "")} for m in members]


@router.post("/{project_id}/organizations/{org_id}/members")
async def add_member(
    project_id: int, org_id: int, req: MemberCreateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """添加成员（角色加入组织）。"""
    await get_user_project(db, project_id, user)
    # 检查角色是否已在该组织
    existing = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.character_id == req.character_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "该角色已在此组织中")
    m = OrganizationMember(
        project_id=project_id, organization_id=org_id,
        source="manual", **req.model_dump(),
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m.to_dict()


@router.put("/{project_id}/organizations/{org_id}/members/{member_id}")
async def update_member(
    project_id: int, org_id: int, member_id: int, req: dict,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    m = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org_id,
            OrganizationMember.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "成员记录不存在")
    for k in ["position", "rank", "status", "loyalty", "contribution", "joined_at", "left_at", "notes"]:
        if k in req:
            setattr(m, k, req[k])
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/organizations/{org_id}/members/{member_id}")
async def remove_member(
    project_id: int, org_id: int, member_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    m = (await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.id == member_id,
            OrganizationMember.organization_id == org_id,
            OrganizationMember.project_id == project_id,
        )
    )).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "成员记录不存在")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


class OrgMembersGenerateReq(BaseModel):
    user_prompt: str = ""


async def _generate_members_for_org(db: AsyncSession, project_id: int, org_id: int, user_prompt: str = "", user_id: int = None) -> list[dict]:
    """AI 为一个组织生成成员的核心逻辑（供单组织和批量端点复用）。"""
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if not org:
        return []
    engine, ai_client = await make_engine_and_client(db, user_id)
    existing_char_ids = [m.character_id for m in (await db.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    )).scalars().all()]
    chars = (await db.execute(
        select(Character).where(
            Character.project_id == project_id,
            ~Character.id.in_(existing_char_ids) if existing_char_ids else True,
        ).limit(30)
    )).scalars().all()
    if not chars:
        return []
    char_list = "\n".join(f"- ID:{c.id} {c.name}（{c.role or '角色'}）" for c in chars)

    prompt = f"""为组织《{org.name}》（类型：{org.org_type or '组织'}）分配成员。

组织简介：{org.description[:200] if org.description else '无'}
可选角色：
{char_list}
{('额外要求：' + user_prompt) if user_prompt else ''}

要求：
1. 从可选角色中选择 3-8 个加入此组织
2. 每个成员包含：character_id(必须是可选角色ID)、position(职位)、rank(等级1-10)、loyalty(忠诚度0-100)、contribution(贡献度0-100)、status("active")
3. 职位要符合组织类型，等级和忠诚度要合理

返回纯JSON数组：[{{"character_id":0,"position":"","rank":5,"loyalty":60,"contribution":40,"status":"active"}}]"""

    result = await ai_client.chat_json_retry(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8, max_tokens=4096,
    )
    if result.get("error"):
        raise HTTPException(500, f"AI 生成失败: {result['error']}")
    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("members") or data.get("data") or []

    char_id_set = {c.id for c in chars}
    created = []
    for m in data:
        if not isinstance(m, dict) or m.get("character_id") not in char_id_set:
            continue
        cid = int(m["character_id"])
        mem = OrganizationMember(
            project_id=project_id, organization_id=org_id,
            character_id=cid,
            position=str(m.get("position", ""))[:100],
            rank=int(m.get("rank", 1)),
            loyalty=int(m.get("loyalty", 50)),
            contribution=int(m.get("contribution", 30)),
            status="active", source="ai",
        )
        db.add(mem)
        # 同步角色的所属组织（如果角色还没有主组织，以此为默认）
        char = await db.get(Character, cid)
        if char and not char.organization_id:
            char.organization_id = org_id
        await db.flush()
        created.append(mem.to_dict())
    await db.commit()
    return created


@router.post("/{project_id}/organizations/{org_id}/members/generate")
async def generate_members(
    project_id: int, org_id: int, req: OrgMembersGenerateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """AI 为组织生成成员（基于现有角色池）。"""
    await get_user_project(db, project_id, user)
    created = await _generate_members_for_org(db, project_id, org_id, req.user_prompt, user.id)
    if not created and not (await db.scalar(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == org_id))):
        raise HTTPException(400, "没有可用角色（所有角色已加入或无角色）")
    return {"count": len(created), "members": created}


@router.post("/{project_id}/organizations/members/generate-all")
async def generate_all_members(
    project_id: int, req: OrgMembersGenerateReq = None,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """一键初始化：为所有组织批量 AI 分配成员。
    
    遍历项目中所有组织，对每个尚未有成员的组织调用 AI 分配。
    返回每个组织的生成结果汇总。
    """
    await get_user_project(db, project_id, user)
    req = req or OrgMembersGenerateReq()
    orgs = (await db.execute(
        select(Organization).where(Organization.project_id == project_id)
    )).scalars().all()
    if not orgs:
        return {"ok": True, "total": 0, "results": []}

    # 所有角色
    chars = (await db.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()
    if not chars:
        return {"ok": True, "total": len(orgs), "results": [], "message": "没有可用角色"}

    # 一次 AI 调用分完所有组织，避免逐个调用导致第一个组织抢走所有好角色
    org_list = "\n".join(
        f"- 组织ID:{o.id} 名称:{o.name} 类型:{o.org_type or '组织'} 简介:{(o.description or '')[:100]}"
        for o in orgs
    )
    char_list = "\n".join(
        f"- ID:{c.id} 姓名:{c.name} 定位:{c.role or '角色'} 性格:{(c.personality or '')[:60]}"
        for c in chars
    )

    engine, ai_client = await make_engine_and_client(db, user.id)
    prompt = f"""将所有角色合理分配到各组织。每个角色至少分配到一个最匹配的组织。
{('额外要求：' + req.user_prompt) if req.user_prompt else ''}

组织列表：
{org_list}

角色列表：
{char_list}

要求：
1. 根据角色定位、性格与组织特征，将每个角色分配到最合适的组织
2. 每个角色至少分配到一个组织，一个角色可以属于多个组织
3. 为每个角色的每个组织身份指定：position(职位)、rank(等级1-10)、loyalty(忠诚度0-100)、contribution(贡献度0-100)
4. 职位要贴合组织类型和角色定位，核心成员等级高、忠诚高

返回JSON对象：
{{"assignments":[{{"character_id":1,"organization_id":2,"position":"长老","rank":8,"loyalty":85,"contribution":60,"status":"active","is_primary":true}}]}}"""

    result = await ai_client.chat_json_retry(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8, max_tokens=8192,
    )
    if result.get("error"):
        raise HTTPException(500, f"AI 生成失败: {result['error']}")
    data = result.get("json") or {}
    assignments = data.get("assignments", []) if isinstance(data, dict) else []
    if isinstance(data, list):
        assignments = data

    org_id_set = {o.id for o in orgs}
    char_id_set = {c.id for c in chars}
    results = []
    by_org: dict[int, int] = {}

    for a in assignments:
        if not isinstance(a, dict):
            continue
        oid = int(a.get("organization_id", 0))
        cid = int(a.get("character_id", 0))
        if oid not in org_id_set or cid not in char_id_set:
            continue
        # 创建成员记录
        mem = OrganizationMember(
            project_id=project_id, organization_id=oid,
            character_id=cid,
            position=str(a.get("position", ""))[:100],
            rank=int(a.get("rank", 5)),
            loyalty=int(a.get("loyalty", 50)),
            contribution=int(a.get("contribution", 30)),
            status="active", source="ai",
        )
        db.add(mem)
        by_org[oid] = by_org.get(oid, 0) + 1
        # 同步角色的所属组织（主组织）
        if a.get("is_primary"):
            char = await db.get(Character, cid)
            if char and not char.organization_id:
                char.organization_id = oid

    await db.commit()

    for o in orgs:
        cnt = by_org.get(o.id, 0)
        results.append({"org_id": o.id, "org_name": o.name, "count": cnt})

    total = sum(r["count"] for r in results)
    return {"ok": True, "total": total, "results": results}
