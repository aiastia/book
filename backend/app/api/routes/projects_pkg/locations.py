"""地点/地图系统路由。

CRUD + AI 生成 + 树形结构查询。接入章节上下文。
"""
import logging
from app.api.routes.projects_pkg.base import *
from app.models.location import Location
from app.models.organization import Organization

logger = logging.getLogger(__name__)
router = make_router()


class LocationCreateReq(BaseModel):
    name: str
    location_type: str = "城市"
    parent_location_id: Optional[int] = None
    level: int = 0
    description: str = ""
    atmosphere: str = ""
    faction_control: str = ""
    faction_org_id: Optional[int] = None
    geography: str = ""
    importance: str = "normal"
    first_appear_chapter: Optional[int] = None
    danger_level: str = "safe"


@router.get("/{project_id}/locations")
async def list_locations(
    project_id: int,
    location_type: str = None,
    parent_id: int = None,
    keyword: str = None,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """列出地点。parent_id=null 返回全部，parent_id=0 返回顶级，parent_id=N 返回子级。"""
    await get_user_project(db, project_id, user)
    q = select(Location).where(Location.project_id == project_id)
    if location_type:
        q = q.where(Location.location_type == location_type)
    if parent_id is not None:
        if parent_id == 0:
            q = q.where(Location.parent_location_id.is_(None))
        else:
            q = q.where(Location.parent_location_id == parent_id)
    if keyword:
        q = q.where(Location.name.like(f"%{keyword}%"))
    q = q.order_by(Location.sort_order.asc(), Location.id.asc())
    locs = (await db.execute(q)).scalars().all()
    return [l.to_dict() for l in locs]


@router.get("/{project_id}/locations/tree")
async def location_tree(
    project_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """获取地点树形结构（带 children 嵌套）。"""
    await get_user_project(db, project_id, user)
    locs = (await db.execute(
        select(Location).where(Location.project_id == project_id)
        .order_by(Location.sort_order.asc(), Location.id.asc())
    )).scalars().all()
    by_id = {l.id: {**l.to_dict(), "children": []} for l in locs}
    roots = []
    for l in locs:
        node = by_id[l.id]
        if l.parent_location_id and l.parent_location_id in by_id:
            by_id[l.parent_location_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


@router.post("/{project_id}/locations")
async def create_location(
    project_id: int, req: LocationCreateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)
    # 自动算层级
    level = req.level
    if req.parent_location_id:
        parent = (await db.execute(
            select(Location).where(Location.id == req.parent_location_id)
        )).scalar_one_or_none()
        if parent:
            level = parent.level + 1
    loc = Location(project_id=project_id, source="manual", level=level, **req.model_dump(exclude={"level"}))
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return loc.to_dict()


@router.put("/{project_id}/locations/{location_id}")
async def update_location(
    project_id: int, location_id: int, req: dict,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    loc = (await db.execute(
        select(Location).where(Location.id == location_id, Location.project_id == project_id)
    )).scalar_one_or_none()
    if not loc:
        raise HTTPException(404, "地点不存在")
    for k in ["name", "location_type", "parent_location_id", "description", "atmosphere",
              "faction_control", "faction_org_id", "geography", "importance",
              "first_appear_chapter", "danger_level", "sort_order"]:
        if k in req:
            setattr(loc, k, req[k])
    # 重算层级
    if req.get("parent_location_id") is not None:
        if req["parent_location_id"]:
            parent = (await db.execute(select(Location).where(Location.id == req["parent_location_id"]))).scalar_one_or_none()
            loc.level = (parent.level + 1) if parent else 0
        else:
            loc.level = 0
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/locations/{location_id}")
async def delete_location(
    project_id: int, location_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    loc = (await db.execute(
        select(Location).where(Location.id == location_id, Location.project_id == project_id)
    )).scalar_one_or_none()
    if not loc:
        raise HTTPException(404, "地点不存在")
    # 子地点提升为顶级（避免孤立）
    children = (await db.execute(
        select(Location).where(Location.parent_location_id == location_id, Location.project_id == project_id)
    )).scalars().all()
    for c in children:
        c.parent_location_id = loc.parent_location_id
        c.level = loc.level
    await db.delete(loc)
    await db.commit()
    return {"ok": True}


class LocationGenerateReq(BaseModel):
    count: int = 5
    location_type: str = ""
    parent_location_id: Optional[int] = None
    user_prompt: str = ""


@router.post("/{project_id}/locations/generate")
async def generate_locations(
    project_id: int, req: LocationGenerateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """AI 批量生成地点。"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    # 父地点信息
    parent_info = ""
    if req.parent_location_id:
        parent = (await db.execute(select(Location).where(Location.id == req.parent_location_id))).scalar_one_or_none()
        if parent:
            parent_info = f"父级地点：{parent.name}（{parent.description[:100]}）"

    prompt = f"""你是网文世界观设定专家。为小说《{proj.title}》设计 {req.count} 个{('「' + req.location_type + '」类') if req.location_type else ''}地点。

题材：{proj.genre or '网文'}
世界观：{proj.synopsis or '（未设定）'}
{parent_info}
{('额外要求：' + req.user_prompt) if req.user_prompt else ''}

要求：
1. 每个地点包含：name(名称)、location_type(类型：城市/区域/建筑/秘境/自然景观/国家/大陆)、description(100-200字)、atmosphere(氛围特色)、faction_control(控制势力)、importance(重要性：minor/normal/major/key)、danger_level(危险等级：safe/dangerous/forbidden/unknown)
2. 重要地点(importance=major或key)至少1个
3. 地点名要有网文特色，符合题材世界观
4. 氛围描述要生动

返回纯JSON数组：[{{"name":"","location_type":"","description":"","atmosphere":"","faction_control":"","importance":"normal","danger_level":"safe"}}]"""

    result = await ai_client.chat_json_retry(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
        max_tokens=8192,
    )
    if result.get("error"):
        raise HTTPException(500, f"AI 生成失败: {result['error']}")
    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("locations") or data.get("data") or []

    created = []
    for l in data[:req.count * 2]:
        if not isinstance(l, dict) or not l.get("name"):
            continue
        try:
            loc = Location(
                project_id=project_id,
                name=str(l.get("name", ""))[:100],
                location_type=str(l.get("location_type", "城市"))[:50],
                description=str(l.get("description", ""))[:2000],
                atmosphere=str(l.get("atmosphere", ""))[:500],
                faction_control=str(l.get("faction_control", ""))[:200],
                importance=str(l.get("importance", "normal"))[:20],
                danger_level=str(l.get("danger_level", "safe"))[:20],
                parent_location_id=req.parent_location_id,
                level=0,
                source="ai",
            )
            db.add(loc)
            await db.flush()
            created.append(loc.to_dict())
        except Exception as e:
            logger.warning(f"[location] 解析单条失败: {e}")
    await db.commit()
    return {"count": len(created), "locations": created}
