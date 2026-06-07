"""角色关系：CRUD / 图谱 / 自动重建（AI 解析角色间关系）"""
import json
from app.api.routes.projects_pkg.base import *
from app.models.character import CharacterRelation


router = make_router()


def _map_category(relation_type: str) -> str:
    """根据关系类型推断分类"""
    t = (relation_type or "").lower()
    family = ["父", "母", "兄", "弟", "姐", "妹", "子", "女", "亲", "族", "祖"]
    hostile = ["敌", "仇", "对手", "反派"]
    romantic = ["恋", "爱", "情", "婚", "妻", "夫", "情侣"]
    prof = ["师", "徒", "上下级", "同事", "同门", "雇佣"]
    if any(k in t for k in family):
        return "family"
    if any(k in t for k in hostile):
        return "hostile"
    if any(k in t for k in romantic):
        return "romantic"
    if any(k in t for k in prof):
        return "professional"
    return "social"


@router.get("/{project_id}/relations")
async def list_relations(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """列出所有角色关系（附带角色名，供图谱渲染）"""
    await get_user_project(db, project_id, user)
    rels = (await db.execute(select(CharacterRelation).where(CharacterRelation.project_id == project_id))).scalars().all()
    # 批量查角色名
    char_ids = set()
    for r in rels:
        char_ids.add(r.from_character_id)
        char_ids.add(r.to_character_id)
    name_map = {}
    if char_ids:
        chars = (await db.execute(select(Character).where(Character.id.in_(char_ids)))).scalars().all()
        name_map = {c.id: c.name for c in chars}
    return [r.to_dict(name_map.get(r.from_character_id), name_map.get(r.to_character_id)) for r in rels]


@router.get("/{project_id}/relations/graph")
async def get_relation_graph(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """关系图谱数据：节点(角色) + 边(关系)，供前端渲染网络图"""
    await get_user_project(db, project_id, user)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    rels = (await db.execute(select(CharacterRelation).where(CharacterRelation.project_id == project_id))).scalars().all()
    char_ids = {c.id for c in chars}
    return {
        "nodes": [{"id": c.id, "name": c.name, "role": c.role} for c in chars],
        "edges": [
            {
                "source": r.from_character_id, "target": r.to_character_id,
                "relation_type": r.relation_type, "intimacy": r.intimacy,
                "category": r.category, "status": r.status,
            }
            for r in rels
            if r.from_character_id in char_ids and r.to_character_id in char_ids
        ],
    }


@router.post("/{project_id}/relations")
async def create_relation(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """手动创建一条关系"""
    await get_user_project(db, project_id, user)
    rel = CharacterRelation(
        project_id=project_id,
        from_character_id=req["from_character_id"],
        to_character_id=req["to_character_id"],
        relation_type=req.get("relation_type", "相识"),
        category=req.get("category") or _map_category(req.get("relation_type", "")),
        intimacy=int(req.get("intimacy", 0)),
        status=req.get("status", "active"),
        description=req.get("description", ""),
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return {"id": rel.id}


@router.put("/{project_id}/relations/{relation_id}")
async def update_relation(project_id: int, relation_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    r = (await db.execute(select(CharacterRelation).where(CharacterRelation.id == relation_id, CharacterRelation.project_id == project_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "关系不存在")
    for k in ["relation_type", "category", "intimacy", "status", "description"]:
        if k in req:
            setattr(r, k, req[k])
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/relations/{relation_id}")
async def delete_relation(project_id: int, relation_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    r = (await db.execute(select(CharacterRelation).where(CharacterRelation.id == relation_id, CharacterRelation.project_id == project_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "关系不存在")
    await db.delete(r)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/relations/auto-rebuild")
async def auto_rebuild_relations(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """AI 自动分析角色关系网并重建。

    流程：读取所有角色 → 让 AI 分析两两关系 → upsert 到关系表。
    移植自 MuMuAINovel 批量角色生成后的关系清理逻辑。
    """
    proj = await get_user_project(db, project_id, user)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    if len(chars) < 2:
        raise HTTPException(400, "至少需要 2 个角色才能分析关系")

    # 构造角色上下文给 AI
    chars_info = "\n".join([
        f"- ID:{c.id} 姓名:{c.name} 身份:{c.role} 性格:{c.personality[:80] or '未知'} 背景:{c.background[:80] or '未知'}"
        for c in chars
    ])

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await ai_client.chat_json_retry(messages=[
        {"role": "system", "content": (
            "你是资深小说编辑。根据角色信息，分析他们之间合理的关系网络。"
            "只返回纯 JSON，格式 {\"relations\": [{\"from_id\": 数字, \"to_id\": 数字, "
            "\"relation_type\": \"关系名(如师徒/恋人/宿敌/父子)\", \"intimacy\": -100到100整数, "
            "\"description\": \"简短描述\"}]}。from_id/to_id 必须是上面给出的真实角色 ID。"
        )},
        {"role": "user", "content": f"小说《{proj.title}》（{proj.genre}）的角色列表：\n{chars_info}\n\n请分析这些角色之间的关系。"},
    ], temperature=0.5, max_retries=3)

    check_skill_error(result)
    data = result.get("json") or {}
    ai_relations = data.get("relations", []) if isinstance(data, dict) else []

    # 建立 id → character 映射，过滤无效引用
    id_set = {c.id for c in chars}
    valid_rels = []
    seen = set()
    for rel in ai_relations:
        if not isinstance(rel, dict):
            continue
        fid, tid = rel.get("from_id"), rel.get("to_id")
        if fid not in id_set or tid not in id_set or fid == tid:
            continue  # 清理无效/自引用（移植自原项目的幻觉清理）
        key = (fid, tid, rel.get("relation_type", "相识"))
        if key in seen:
            continue
        seen.add(key)
        valid_rels.append(rel)

    # 清空旧关系，写入新关系
    old_rels = (await db.execute(select(CharacterRelation).where(CharacterRelation.project_id == project_id))).scalars().all()
    for old in old_rels:
        await db.delete(old)

    created = []
    for rel in valid_rels:
        rtype = str(rel.get("relation_type", "相识"))
        r = CharacterRelation(
            project_id=project_id,
            from_character_id=rel["from_id"],
            to_character_id=rel["to_id"],
            relation_type=rtype,
            category=_map_category(rtype),
            intimacy=int(rel.get("intimacy", 0)),
            description=str(rel.get("description", "")),
        )
        db.add(r)
        created.append(r)
    await db.commit()
    return {"count": len(created), "relations": [r.relation_type for r in created]}
