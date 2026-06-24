"""角色关系：CRUD / 图谱 / 自动重建（AI 解析角色间关系）"""
import asyncio
import json
import logging
from app.api.routes.projects_pkg.base import *
from app.models.character import CharacterRelation


router = make_router()
logger = logging.getLogger(__name__)


# ===== 关系向量同步 =====

async def _sync_relation_memory(project_id: int, relation_id: int, user_id: int):
    """创建或更新关系对应的向量记忆。"""
    try:
        from app.models.story_memory import StoryMemory
        from app.services.memory_vector_service import MemoryVectorService, _embed_one
        async with async_session() as s:
            # 查关系详情 + 角色名
            rel = (await s.execute(
                select(CharacterRelation).where(CharacterRelation.id == relation_id, CharacterRelation.project_id == project_id)
            )).scalar_one_or_none()
            if not rel:
                return
            names = {}
            for cid in [rel.from_character_id, rel.to_character_id]:
                if cid:
                    c = (await s.execute(select(Character).where(Character.id == cid))).scalar_one_or_none()
                    if c:
                        names[cid] = c.name
            from_name = names.get(rel.from_character_id, f"角色#{rel.from_character_id}")
            to_name = names.get(rel.to_character_id, f"角色#{rel.to_character_id}")
            title_prefix = f"[relation:{relation_id}]"
            # 删旧
            old = (await s.execute(
                select(StoryMemory).where(
                    StoryMemory.project_id == project_id,
                    StoryMemory.title.like(f"{title_prefix}%"),
                )
            )).scalars().all()
            for o in old:
                await s.delete(o)
            # 建新
            memory_text = f"【{rel.relation_type}】{from_name} → {to_name}"
            if rel.description:
                memory_text += f"\n{rel.description}"
            m = StoryMemory(
                project_id=project_id, user_id=user_id,
                memory_type="relationship", title=f"{title_prefix} {from_name}与{to_name}的关系",
                content=memory_text, importance=0.6,
                related_characters=[from_name, to_name],
            )
            s.add(m)
            await s.commit()
            await s.refresh(m)
            try:
                vec = await _embed_one(memory_text[:2000])
                if vec:
                    vs = MemoryVectorService()
                    await vs.add_memory(
                        user_id=user_id or 0, project_id=project_id, memory_id=m.id,
                        content=memory_text, memory_type="relationship",
                        title=m.title, importance=0.6,
                    )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[relation] 向量同步失败 relation_id={relation_id}: {e}")


async def _delete_relation_memory(project_id: int, relation_id: int):
    """删除关系对应的向量记忆。"""
    try:
        from app.models.story_memory import StoryMemory
        async with async_session() as s:
            title_prefix = f"[relation:{relation_id}]"
            old = (await s.execute(
                select(StoryMemory).where(
                    StoryMemory.project_id == project_id,
                    StoryMemory.title.like(f"{title_prefix}%"),
                )
            )).scalars().all()
            for o in old:
                await s.delete(o)
            await s.commit()
    except Exception as e:
        logger.warning(f"[relation] 删除向量记忆失败 relation_id={relation_id}: {e}")


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
    asyncio.ensure_future(_delete_relation_memory(project_id, relation_id))
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
        # intimacy 容错：非数字时回退 0
        raw_intimacy = rel.get("intimacy", 0)
        try:
            intimacy_val = int(raw_intimacy)
        except (TypeError, ValueError):
            intimacy_val = 0
        r = CharacterRelation(
            project_id=project_id,
            from_character_id=rel["from_id"],
            to_character_id=rel["to_id"],
            relation_type=rtype,
            category=_map_category(rtype),
            intimacy=intimacy_val,
            description=str(rel.get("description", "")),
        )
        db.add(r)
        created.append(r)
    await db.commit()
    return {"count": len(created), "relations": [r.relation_type for r in created]}


# ============ 关系变化日志 ============

class RelChangeLogCreate(BaseModel):
    chapter_number: int
    summary: str = ""
    changed_fields: dict = {}


async def _build_relation_snapshot(db: AsyncSession, relation_id: int) -> dict:
    """构建关系的当前完整快照"""
    rel = await db.get(CharacterRelation, relation_id)
    if not rel:
        return {}
    return {c.name: getattr(rel, c.name) for c in rel.__table__.columns
            if c.name not in ('created_at', 'updated_at')}


@router.get("/{project_id}/relations/{relation_id}/change-logs")
async def list_relation_change_logs(
    project_id: int, relation_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """列出关系的所有变化日志（按章节号升序）"""
    await get_user_project(db, project_id, user)
    from app.models.relation_change_log import RelationChangeLog
    logs = (await db.execute(
        select(RelationChangeLog).where(
            RelationChangeLog.project_id == project_id,
            RelationChangeLog.relation_id == relation_id,
        ).order_by(RelationChangeLog.chapter_number.asc())
    )).scalars().all()
    # 补充关系涉及的双方角色名
    rel = await db.get(CharacterRelation, relation_id)
    char_names = {}
    if rel:
        for cid in [rel.from_character_id, rel.to_character_id]:
            if cid:
                c = await db.get(Character, cid)
                if c:
                    char_names[cid] = c.name
    return [{
        **log.to_dict(),
        "from_name": char_names.get(rel.from_character_id, "") if rel else "",
        "to_name": char_names.get(rel.to_character_id, "") if rel else "",
    } for log in logs]


@router.post("/{project_id}/relations/{relation_id}/change-logs")
async def create_relation_change_log(
    project_id: int, relation_id: int, req: RelChangeLogCreate,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """添加一条关系变化日志，自动保存当前关系完整快照"""
    await get_user_project(db, project_id, user)
    from app.models.relation_change_log import RelationChangeLog
    rel = await db.get(CharacterRelation, relation_id)
    if not rel:
        raise HTTPException(404, "关系不存在")
    snapshot = await _build_relation_snapshot(db, relation_id)
    log = RelationChangeLog(
        project_id=project_id,
        relation_id=relation_id,
        chapter_number=req.chapter_number,
        changed_fields=req.changed_fields or {},
        snapshot=snapshot,
        summary=req.summary or "",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log.to_dict()


@router.delete("/{project_id}/relations/{relation_id}/change-logs/{log_id}")
async def delete_relation_change_log(
    project_id: int, relation_id: int, log_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """删除一条关系变化日志"""
    await get_user_project(db, project_id, user)
    from app.models.relation_change_log import RelationChangeLog
    log = (await db.execute(
        select(RelationChangeLog).where(
            RelationChangeLog.id == log_id,
            RelationChangeLog.project_id == project_id,
            RelationChangeLog.relation_id == relation_id,
        )
    )).scalar_one_or_none()
    if not log:
        raise HTTPException(404, "日志不存在")
    await db.delete(log)
    await db.commit()
    return {"ok": True}


async def get_relation_state_at_chapter(db: AsyncSession, project_id: int, relation_id: int, chapter_number: int) -> dict | None:
    """获取关系在指定章节之前的「当时状态」快照。"""
    from app.models.relation_change_log import RelationChangeLog
    log = (await db.execute(
        select(RelationChangeLog).where(
            RelationChangeLog.project_id == project_id,
            RelationChangeLog.relation_id == relation_id,
            RelationChangeLog.chapter_number < chapter_number,
        ).order_by(RelationChangeLog.chapter_number.desc()).limit(1)
    )).scalar_one_or_none()
    return log.snapshot if log else None


# ============ 关系类型管理 ============

class RenameTypeReq(BaseModel):
    old_name: str
    new_name: str


@router.get("/{project_id}/relations/types")
async def list_relation_types(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """列出项目中所有已用的关系类型及其使用次数"""
    await get_user_project(db, project_id, user)
    from sqlalchemy import func
    rows = (await db.execute(
        select(CharacterRelation.relation_type, func.count(CharacterRelation.id))
        .where(CharacterRelation.project_id == project_id)
        .group_by(CharacterRelation.relation_type)
        .order_by(func.count(CharacterRelation.id).desc())
    )).all()
    return [{"name": r[0], "count": r[1]} for r in rows]


@router.put("/{project_id}/relations/types/rename")
async def rename_relation_type(project_id: int, req: RenameTypeReq, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """批量重命名关系类型（将所有旧名称改为新名称）"""
    await get_user_project(db, project_id, user)
    if not req.old_name.strip() or not req.new_name.strip():
        raise HTTPException(400, "名称不能为空")
    if req.old_name == req.new_name:
        return {"ok": True, "updated": 0}
    result = await db.execute(
        select(CharacterRelation).where(
            CharacterRelation.project_id == project_id,
            CharacterRelation.relation_type == req.old_name,
        )
    )
    rels = result.scalars().all()
    count = 0
    for r in rels:
        r.relation_type = req.new_name
        count += 1
    await db.commit()
    return {"ok": True, "updated": count}


@router.delete("/{project_id}/relations/types/{type_name}")
async def delete_relation_type(project_id: int, type_name: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除关系类型（将所有使用该类型的关系改为"相识"）"""
    await get_user_project(db, project_id, user)
    from urllib.parse import unquote
    type_name = unquote(type_name)
    result = await db.execute(
        select(CharacterRelation).where(
            CharacterRelation.project_id == project_id,
            CharacterRelation.relation_type == type_name,
        )
    )
    rels = result.scalars().all()
    count = 0
    for r in rels:
        r.relation_type = "相识"
        count += 1
    await db.commit()
    return {"ok": True, "updated": count}
