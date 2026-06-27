"""记忆系统：列表/检索/统计/删除/手动添加 + 向量语义搜索。

对标 MuMuAINovel memories API。记忆由剧情分析自动提取（见 chapter_service._extract_memories），
此处提供管理接口 + 向量语义检索（ChromaDB + AI embedding）。
"""

import logging

from sqlalchemy import func, or_

from app.api.routes.projects_pkg.base import *
from app.models.story_memory import StoryMemory
from app.services.memory_vector_service import MemoryVectorService

logger = logging.getLogger(__name__)
router = make_router()


def _to_dict(m: StoryMemory) -> dict:
    return {
        "id": m.id,
        "memory_type": m.memory_type,
        "title": m.title or "",
        "content": m.content,
        "chapter_number": m.chapter_number,
        "importance": m.importance,
        "tags": m.tags or [],
        "related_characters": m.related_characters or [],
        "vector_id": m.vector_id or "",
        "has_vector": bool(m.vector_id),
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/{project_id}/memories")
async def list_memories(
    project_id: int,
    memory_type: str = None,
    chapter_number: int = None,
    keyword: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """列出/检索记忆。支持按类型、章节、关键词筛选。"""
    await get_user_project(db, project_id, user)
    q = select(StoryMemory).where(StoryMemory.project_id == project_id)
    if memory_type:
        q = q.where(StoryMemory.memory_type == memory_type)
    if chapter_number:
        q = q.where(StoryMemory.chapter_number == chapter_number)
    if keyword:
        q = q.where(StoryMemory.content.like(f"%{keyword}%"))
    q = q.order_by(StoryMemory.chapter_number.desc(), StoryMemory.importance.desc()).limit(
        min(limit, 200)
    )
    memories = (await db.execute(q)).scalars().all()
    return [_to_dict(m) for m in memories]


@router.get("/{project_id}/memories/stats")
async def memory_stats(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """记忆统计：按类型分组的数量 + 向量化数量 + embedding 模式"""
    await get_user_project(db, project_id, user)
    result = await db.execute(
        select(StoryMemory.memory_type, func.count(StoryMemory.id))
        .where(StoryMemory.project_id == project_id)
        .group_by(StoryMemory.memory_type)
    )
    by_type = {row[0] or "other": row[1] for row in result.all()}
    total = await db.scalar(
        select(func.count(StoryMemory.id)).where(StoryMemory.project_id == project_id)
    )
    vectorized = await db.scalar(
        select(func.count(StoryMemory.id)).where(
            StoryMemory.project_id == project_id,
            StoryMemory.vector_id != "",
        )
    )
    # embedding 模式状态
    from app.services import local_embedding

    embedding_status = local_embedding.get_status()
    return {
        "total": total or 0,
        "by_type": by_type,
        "vectorized": vectorized or 0,
        "embedding": embedding_status,
    }


class MemoryCreateReq(BaseModel):
    memory_type: str = "manual"
    title: str = ""
    content: str = ""
    importance: float = 0.5
    chapter_number: Optional[int] = None
    tags: list = []


@router.post("/{project_id}/memories")
async def create_memory(
    project_id: int,
    req: MemoryCreateReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """手动添加记忆（自动写入向量库）"""
    await get_user_project(db, project_id, user)
    m = StoryMemory(
        user_id=user.id,
        project_id=project_id,
        chapter_number=req.chapter_number,
        memory_type=req.memory_type,
        title=req.title,
        content=req.content,
        importance=req.importance,
        tags=req.tags,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    # 异步写入向量库（失败不阻塞）
    try:
        ai_client = await AIClient.from_user_config(db, user.id)
        vs = MemoryVectorService(ai_client)
        vid = await vs.add_memory(
            user_id=user.id,
            project_id=project_id,
            memory_id=m.id,
            content=m.content,
            memory_type=m.memory_type,
            title=m.title,
            importance=m.importance,
            chapter_number=m.chapter_number,
        )
        if vid:
            m.vector_id = vid
            await db.commit()
    except Exception as e:
        logger.warning(f"[memory] 写入向量失败（不影响创建）: {e}")
    return _to_dict(m)


@router.put("/{project_id}/memories/{memory_id}")
async def update_memory(
    project_id: int,
    memory_id: int,
    req: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    m = (
        await db.execute(
            select(StoryMemory).where(
                StoryMemory.id == memory_id, StoryMemory.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "记忆不存在")
    content_changed = False
    for k in ["memory_type", "title", "content", "importance", "tags"]:
        if k in req:
            setattr(m, k, req[k])
            if k == "content":
                content_changed = True
    await db.commit()
    # 内容变化 → 更新向量
    if content_changed:
        try:
            ai_client = await AIClient.from_user_config(db, user.id)
            vs = MemoryVectorService(ai_client)
            await vs.delete_memory(user.id, project_id, m.id)
            vid = await vs.add_memory(
                user_id=user.id,
                project_id=project_id,
                memory_id=m.id,
                content=m.content,
                memory_type=m.memory_type,
                title=m.title,
                importance=m.importance,
                chapter_number=m.chapter_number,
            )
            m.vector_id = vid or ""
            await db.commit()
        except Exception as e:
            logger.warning(f"[memory] 更新向量失败: {e}")
    return {"ok": True}


@router.delete("/{project_id}/memories/{memory_id}")
async def delete_memory(
    project_id: int,
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    m = (
        await db.execute(
            select(StoryMemory).where(
                StoryMemory.id == memory_id, StoryMemory.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not m:
        raise HTTPException(404, "记忆不存在")
    # 同步删除向量
    try:
        ai_client = await AIClient.from_user_config(db, user.id)
        vs = MemoryVectorService(ai_client)
        await vs.delete_memory(user.id, project_id, m.id)
    except Exception as e:
        logger.warning(f"[memory] 删除向量失败: {e}")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/memories")
async def clear_memories(
    project_id: int,
    memory_type: str = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """清空记忆（可按类型）。同步清理向量库。"""
    await get_user_project(db, project_id, user)
    q = select(StoryMemory).where(StoryMemory.project_id == project_id)
    if memory_type:
        q = q.where(StoryMemory.memory_type == memory_type)
    memories = (await db.execute(q)).scalars().all()
    # 若没指定类型 → 删整个 collection；否则逐条删
    try:
        ai_client = await AIClient.from_user_config(db, user.id)
        vs = MemoryVectorService(ai_client)
        if not memory_type:
            await vs.delete_project(user.id, project_id)
        else:
            for m in memories:
                await vs.delete_memory(user.id, project_id, m.id)
    except Exception as e:
        logger.warning(f"[memory] 清空向量失败: {e}")
    for m in memories:
        await db.delete(m)
    await db.commit()
    return {"deleted": len(memories)}


class SemanticSearchReq(BaseModel):
    query: str
    memory_types: Optional[list[str]] = None
    limit: int = 10
    min_importance: float = 0.0


@router.post("/{project_id}/memories/search")
async def semantic_search(
    project_id: int,
    req: SemanticSearchReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """向量语义搜索记忆（对标 MuMu memory_service.search_memories）。

    输入 query，返回语义最相关的记忆（带相似度分数）。
    """
    await get_user_project(db, project_id, user)
    if not req.query.strip():
        return []
    try:
        ai_client = await AIClient.from_user_config(db, user.id)
        vs = MemoryVectorService(ai_client)
        results = await vs.search(
            user_id=user.id,
            project_id=project_id,
            query=req.query,
            memory_types=req.memory_types,
            limit=req.limit,
            min_importance=req.min_importance,
        )
        return results
    except Exception as e:
        logger.error(f"[memory] 语义搜索失败: {e}")
        raise HTTPException(500, f"语义搜索失败: {e}")


@router.post("/{project_id}/memories/reindex")
async def reindex_vectors(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """重建项目记忆的向量索引（为已有记忆批量生成向量）。

    用于：开启向量检索后，给历史记忆补向量。
    """
    await get_user_project(db, project_id, user)
    memories = (
        (
            await db.execute(
                select(StoryMemory).where(
                    StoryMemory.project_id == project_id,
                    or_(StoryMemory.vector_id == "", StoryMemory.vector_id.is_(None)),
                )
            )
        )
        .scalars()
        .all()
    )
    if not memories:
        return {"indexed": 0, "total": 0}
    ai_client = await AIClient.from_user_config(db, user.id)
    vs = MemoryVectorService(ai_client)
    ok = 0
    for m in memories:
        try:
            vid = await vs.add_memory(
                user_id=user.id,
                project_id=project_id,
                memory_id=m.id,
                content=m.content,
                memory_type=m.memory_type,
                title=m.title,
                importance=m.importance,
                chapter_number=m.chapter_number,
            )
            if vid:
                m.vector_id = vid
                m.user_id = user.id
                ok += 1
        except Exception as e:
            logger.warning(f"[memory] 重建单条向量失败 id={m.id}: {e}")
    await db.commit()
    return {"indexed": ok, "total": len(memories)}
