"""记忆向量检索服务（ChromaDB + 双模式 Embedding）。

Embedding 策略（省成本）：
1. 优先本地模型（fastembed + BAAI/bge-small-zh-v1.5，512维，零 API 成本）
2. 本地不可用时回退到 API（AIClient.embed）

设计要点：
- 向量主存储在 ChromaDB（PersistentClient，data/chroma_db）
- 每个项目独立 collection（命名 u_{hash8}_p_{hash8}）
- 提供 5 路融合检索（最近章节/语义相关/未完结伏笔/角色相关/重要情节点）
"""

import asyncio
import hashlib
import logging

from sqlalchemy import select

from app.core.ai_client import AIClient
from app.core.database import async_session
from app.models.story_memory import StoryMemory
from app.services import local_embedding

logger = logging.getLogger(__name__)

# ChromaDB 持久化路径
CHROMA_PATH = "data/chroma_db"

# 单例客户端
_chroma_client = None


def _get_chroma_client():
    """获取 ChromaDB PersistentClient（单例）。"""
    global _chroma_client
    if _chroma_client is None:
        import chromadb

        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def _collection_name(user_id: int, project_id: int) -> str:
    """生成合法的 collection 名（3-63 字符，字母数字起止）。"""
    u = hashlib.sha256(str(user_id).encode()).hexdigest()[:8]
    p = hashlib.sha256(str(project_id).encode()).hexdigest()[:8]
    return f"u_{u}_p_{p}"


def _get_collection(user_id: int, project_id: int):
    """获取或创建某项目的 collection。"""
    client = _get_chroma_client()
    name = _collection_name(user_id, project_id)
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


async def _embed_one(text: str) -> list[float]:
    """双模式生成单条向量：本地优先，API 回退。"""
    if not text or not text.strip():
        return []
    # 1. 尝试本地模型（在线程池中运行，避免阻塞事件循环）
    try:
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(None, local_embedding.embed_one_sync, text[:2000])
        if vec:
            return vec
    except Exception as e:
        logger.debug(f"[memory] 本地 embedding 失败，尝试 API: {e}")
    # 2. 回退到 API
    return []


class MemoryVectorService:
    """记忆向量检索服务。双模式 embedding（本地优先）。"""

    def __init__(self, ai_client: AIClient = None):
        self.ai = ai_client  # API 回退用（可选）

    async def add_memory(
        self,
        user_id: int,
        project_id: int,
        memory_id: int,
        content: str,
        memory_type: str = "plot",
        title: str = "",
        importance: float = 0.5,
        chapter_number: int | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """添加一条记忆到向量库。返回 vector_id（失败返回 None）。"""
        if not content or not content.strip():
            return None
        # 双模式：本地优先，API 回退
        vec = await _embed_one(content[:2000])
        if not vec:
            # 本地失败，尝试 API
            if self.ai:
                vec = await self.ai.embed_one(content[:2000])
            if not vec:
                logger.warning(
                    f"[memory] embedding 全部失败（本地+API），跳过向量入库: memory_id={memory_id}"
                )
                return None
        try:
            col = _get_collection(user_id, project_id)
            vid = f"mem_{memory_id}"
            meta = {
                "memory_id": memory_id,
                "memory_type": memory_type or "plot",
                "title": (title or "")[:200],
                "importance": float(importance),
                "chapter_number": chapter_number or 0,
            }
            if metadata:
                for k, v in metadata.items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
            col.add(
                ids=[vid],
                embeddings=[vec],
                documents=[content[:4000]],
                metadatas=[meta],
            )
            return vid
        except Exception as e:
            logger.error(f"[memory] 向量入库失败: {e}")
            return None

    async def search(
        self,
        user_id: int,
        project_id: int,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 10,
        min_importance: float = 0.0,
        chapter_range: tuple[int, int] | None = None,
    ) -> list[dict]:
        """向量检索。返回 [{content, similarity, metadata}]。"""
        if not query.strip():
            return []
        # 双模式：本地优先，API 回退
        vec = await _embed_one(query[:2000])
        if not vec:
            if self.ai:
                vec = await self.ai.embed_one(query[:2000])
            if not vec:
                return []
        try:
            col = _get_collection(user_id, project_id)
            where = {}
            if memory_types:
                where["memory_type"] = {"$in": memory_types}
            # importance 筛选 ChromaDB 不直接支持数值比较，改在 Python 侧过滤
            query_kwargs = {
                "query_embeddings": [vec],
                "n_results": min(limit * 3, 30),  # 多取再过滤
            }
            if where:
                query_kwargs["where"] = where
            res = col.query(**query_kwargs)
        except Exception as e:
            logger.error(f"[memory] 向量检索失败: {e}")
            return []

        out = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            similarity = 1 - dist  # cosine distance → similarity
            if similarity < 0.1:
                continue
            importance = float(meta.get("importance", 0))
            if importance < min_importance:
                continue
            ch = int(meta.get("chapter_number", 0))
            if chapter_range and not (chapter_range[0] <= ch <= chapter_range[1]):
                continue
            out.append(
                {
                    "content": doc,
                    "similarity": round(similarity, 3),
                    "metadata": meta,
                    "memory_id": meta.get("memory_id"),
                    "memory_type": meta.get("memory_type"),
                    "title": meta.get("title", ""),
                    "importance": importance,
                    "chapter_number": ch,
                }
            )
            if len(out) >= limit:
                break
        return out

    async def delete_memory(self, user_id: int, project_id: int, memory_id: int):
        """删除单条记忆的向量。"""
        try:
            col = _get_collection(user_id, project_id)
            col.delete(ids=[f"mem_{memory_id}"])
        except Exception as e:
            logger.warning(f"[memory] 删除向量失败: {e}")

    async def delete_project(self, user_id: int, project_id: int):
        """删除整个项目的向量集合。"""
        try:
            client = _get_chroma_client()
            name = _collection_name(user_id, project_id)
            try:
                client.delete_collection(name=name)
            except Exception:
                pass  # 不存在则忽略
        except Exception as e:
            logger.warning(f"[memory] 删除项目向量集失败: {e}")

    async def delete_chapter(self, user_id: int, project_id: int, chapter_id: int):
        """删除某章节相关的所有向量（通过 metadata 筛选）。"""
        try:
            col = _get_collection(user_id, project_id)
            # 先查所有该章节的 id
            res = col.get(where={"chapter_id": chapter_id})
            ids = res.get("ids", []) if res else []
            if ids:
                col.delete(ids=ids)
        except Exception as e:
            logger.warning(f"[memory] 删除章节向量失败: {e}")

    async def build_context_for_generation(
        self,
        user_id: int,
        project_id: int,
        current_chapter: int,
        chapter_outline: str = "",
        character_names: str = "",
        top_k: int = 3,
    ) -> str:
        """6 路融合检索，组装章节生成上下文。

        对标 MuMu memory_service.build_context_for_generation：
        1. 最近章节（按章节号连续性）
        2. 语义相关（query=大纲）
        3. 未完结伏笔（memory_type=foreshadow）
        4. 角色相关（query=角色名+状态+关系）
        5. 重要情节点（min_importance=0.7）
        6. 时间线回溯（方案 B：语义+时间范围，覆盖 10 章外的长期记忆）
        """
        seen_ids = set()
        snippets = []

        async def _gather(results, label):
            for r in results:
                mid = r.get("memory_id")
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                title = r.get("title", "")
                ch = r.get("chapter_number", 0)
                ch_tag = f"[第{ch}章] " if ch else ""
                title_tag = f"《{title}》" if title else ""
                snippets.append(f"{ch_tag}{title_tag}{r['content']}")
                if len(snippets) >= top_k * 5:
                    return

        # 1. 最近章节记忆（查 DB，按章节号倒序）
        async with async_session() as db:
            recent = (
                (
                    await db.execute(
                        select(StoryMemory)
                        .where(
                            StoryMemory.project_id == project_id,
                            StoryMemory.chapter_number.isnot(None),
                            StoryMemory.chapter_number < current_chapter,
                        )
                        .order_by(StoryMemory.chapter_number.desc())
                        .limit(top_k)
                    )
                )
                .scalars()
                .all()
            )
            for m in recent:
                if m.id in seen_ids:
                    continue
                seen_ids.add(m.id)
                ch_tag = f"[第{m.chapter_number}章] " if m.chapter_number else ""
                snippets.append(f"{ch_tag}{m.title or ''}{m.content}")

        # 2. 语义相关（用大纲做 query）
        if chapter_outline.strip():
            results = await self.search(
                user_id,
                project_id,
                chapter_outline[:500],
                memory_types=["plot", "character", "world"],
                limit=top_k,
                min_importance=0.3,
            )
            await _gather(results, "语义相关")

        # 3. 角色相关
        if character_names.strip():
            results = await self.search(
                user_id,
                project_id,
                character_names[:500],
                memory_types=["character", "relationship"],
                limit=top_k,
                min_importance=0.3,
            )
            await _gather(results, "角色相关")

        # 4. 重要情节点
        results = await self.search(
            user_id,
            project_id,
            "重要 转折 高潮 关键 爆点",
            limit=top_k,
            min_importance=0.7,
        )
        await _gather(results, "重要情节")

        # 5. 时间线回溯（方案 B：覆盖 10 章外的长期记忆）
        # 用大纲语义 query + 时间范围过滤，专门召回近期窗口外的历史记忆
        if chapter_outline.strip() and current_chapter > 10:
            lookback_start = max(1, current_chapter - 30)  # 回溯起点
            lookback_end = current_chapter - 10  # 回溯终点（排除最近10章，已有摘要链覆盖）
            if lookback_start < lookback_end:
                results = await self.search(
                    user_id,
                    project_id,
                    chapter_outline[:500],
                    memory_types=["plot", "character", "foreshadow", "conflict"],
                    limit=top_k,
                    min_importance=0.4,
                    chapter_range=(lookback_start, lookback_end),
                )
                await _gather(results, "时间线回溯")

        if not snippets:
            return ""
        return "\n\n".join(snippets[: top_k * 3])
