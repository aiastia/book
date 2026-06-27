"""物品/道具系统路由。

CRUD + AI 批量生成。接入章节上下文（持有物品）。
"""

import logging

from app.api.routes.projects_pkg.base import *
from app.models.character import Character
from app.models.item import Item

logger = logging.getLogger(__name__)
router = make_router()


class ItemCreateReq(BaseModel):
    name: str
    category: str = "装备"
    rarity: str = "common"
    item_type: str = ""
    description: str = ""
    attributes: dict = {}
    owner_character_id: Optional[int] = None
    owner_name: str = ""
    obtained_chapter: Optional[int] = None
    obtained_description: str = ""
    status: str = "in_use"
    is_key_item: int = 0
    quantity: int = 1


def _resolve_owner_name(db_obj: Item, char_map: dict) -> str:
    if db_obj.owner_name:
        return db_obj.owner_name
    if db_obj.owner_character_id and db_obj.owner_character_id in char_map:
        return char_map[db_obj.owner_character_id]
    return ""


@router.get("/{project_id}/items")
async def list_items(
    project_id: int,
    category: str = None,
    rarity: str = None,
    owner_id: int = None,
    keyword: str = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """列出物品。支持按分类/稀有度/持有者/关键词筛选。"""
    await get_user_project(db, project_id, user)
    q = select(Item).where(Item.project_id == project_id)
    if category:
        q = q.where(Item.category == category)
    if rarity:
        q = q.where(Item.rarity == rarity)
    if owner_id:
        q = q.where(Item.owner_character_id == owner_id)
    if keyword:
        q = q.where(Item.name.like(f"%{keyword}%"))
    q = q.order_by(Item.is_key_item.desc(), Item.rarity.desc(), Item.id.asc())
    items = (await db.execute(q)).scalars().all()
    # 解析持有者名
    char_ids = [i.owner_character_id for i in items if i.owner_character_id]
    char_map = {}
    if char_ids:
        chars = (
            (await db.execute(select(Character).where(Character.id.in_(char_ids)))).scalars().all()
        )
        char_map = {c.id: c.name for c in chars}
    return [{**i.to_dict(), "owner_name": _resolve_owner_name(i, char_map)} for i in items]


@router.post("/{project_id}/items")
async def create_item(
    project_id: int,
    req: ItemCreateReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)
    item = Item(project_id=project_id, source="manual", **req.model_dump(exclude_none=False))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item.to_dict()


@router.put("/{project_id}/items/{item_id}")
async def update_item(
    project_id: int,
    item_id: int,
    req: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    item = (
        await db.execute(select(Item).where(Item.id == item_id, Item.project_id == project_id))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "物品不存在")
    for k in [
        "name",
        "category",
        "rarity",
        "item_type",
        "description",
        "attributes",
        "owner_character_id",
        "owner_name",
        "obtained_chapter",
        "obtained_description",
        "status",
        "is_key_item",
        "quantity",
    ]:
        if k in req:
            setattr(item, k, req[k])
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/items/{item_id}")
async def delete_item(
    project_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    item = (
        await db.execute(select(Item).where(Item.id == item_id, Item.project_id == project_id))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "物品不存在")
    await db.delete(item)
    await db.commit()
    return {"ok": True}


class ItemGenerateReq(BaseModel):
    count: int = 6
    category: str = ""  # 指定分类，空=混合
    user_prompt: str = ""  # 额外需求


@router.post("/{project_id}/items/generate")
async def generate_items(
    project_id: int,
    req: ItemGenerateReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """AI 批量生成物品（通过 SkillEngine 使用统一模板）。"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)

    # 角色名供 AI 关联持有者
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id).limit(20)))
        .scalars()
        .all()
    )
    char_names = "、".join(c.name for c in chars) if chars else "暂无"

    # 构建完整世界观上下文
    world_parts = []
    if proj.world_time_period:
        world_parts.append(f"时间：{proj.world_time_period}")
    if proj.world_location:
        world_parts.append(f"地点：{proj.world_location}")
    if proj.world_atmosphere:
        world_parts.append(f"氛围：{proj.world_atmosphere}")
    if proj.world_rules:
        world_parts.append(f"规则：{proj.world_rules}")
    world_info = "\n".join(world_parts) if world_parts else f"简介：{proj.synopsis or '暂无'}"

    user_prompt = f"请生成{req.count}个{('「' + req.category + '」类') if req.category else ''}物品。\n主要角色：{char_names}"
    if req.user_prompt:
        user_prompt += f"\n额外要求：{req.user_prompt}"

    result = await engine.execute_skill(
        "items_generate",
        ai_client,
        {
            "title": proj.title,
            "world_info": world_info,
            "user_prompt": user_prompt,
        },
    )

    if result.get("error"):
        raise HTTPException(500, f"AI 生成失败: {result['error']}")
    data = result.get("json") or []
    # 防御性解析（AI 可能返回 {items:[...]}）
    if isinstance(data, dict):
        data = data.get("items") or data.get("data") or []

    created = []
    for it in data[: req.count * 2]:  # 上限保护
        if not isinstance(it, dict) or not it.get("name"):
            continue
        try:
            item = Item(
                project_id=project_id,
                name=str(it.get("name", ""))[:100],
                category=str(it.get("category", "装备"))[:50],
                rarity=str(it.get("rarity", "common"))[:20],
                item_type=str(it.get("item_type", ""))[:50],
                description=str(it.get("description", ""))[:2000],
                attributes=it.get("attributes", {})
                if isinstance(it.get("attributes"), dict)
                else {},
                is_key_item=1 if it.get("is_key_item") else 0,
                status="stored",
                source="ai",
            )
            db.add(item)
            await db.flush()
            created.append(item.to_dict())
        except Exception as e:
            logger.warning(f"[item] 解析单条失败: {e}")
    await db.commit()
    return {"count": len(created), "items": created}
