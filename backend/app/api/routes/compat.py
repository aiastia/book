"""前端兼容路由（扁平化 API）

前端目前设计为"扁平化全局接口"（如 /api/books、/api/characters），
而核心业务模型是"项目级"（/api/projects/{id}/...）。
本模块提供桥接层，把前端接口映射到现有模型，降低联调成本。

策略：
- "当前项目"= 用户最近更新的项目（前端暂无项目切换 UI）
- 鉴权宽松：有 token 验证用户；无 token 时回退到首个用户（仅开发联调用）
- 只读接口为主，覆盖前端各页面已声明的 GET 请求
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decode_token
from app.core.database import get_db
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.generation_history import GenerationHistory
from app.models.outline import Outline
from app.models.project import Project
from app.models.prompt_template import PromptTemplate
from app.models.user import User
from app.models.world import WorldSetting

router = APIRouter(prefix="/api", tags=["前端兼容"])
_security = HTTPBearer(auto_error=False)


# ---------- 鉴权（开发模式宽松） ----------
async def get_user_dev(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """有 token 验证用户；无 token 回退到第一个用户（仅开发联调）。"""
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            uid = payload.get("sub")
            if uid:
                u = (await db.execute(select(User).where(User.id == int(uid)))).scalar_one_or_none()
                if u:
                    return u
        except Exception:
            pass
    # 无 token：回退到第一个用户
    return (await db.execute(select(User).limit(1))).scalar_one_or_none()


async def _current_project(db: AsyncSession, user: User) -> Project | None:
    """获取用户最近活跃项目，没有则返回 None。"""
    if not user:
        return None
    return (
        await db.execute(
            select(Project)
            .where(Project.user_id == user.id)
            .order_by(Project.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _badge_for(status: str) -> str:
    """根据状态映射成前端 badge 类型。"""
    mapping = {
        "completed": "success",
        "published": "success",
        "active": "success",
        "draft": "warning",
        "paused": "warning",
        "pending": "warning",
        "polishing": "info",
        "failed": "danger",
        "archived": "info",
    }
    return mapping.get((status or "").lower(), "info")


# ---------- 兼容登录 ----------
class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def compat_login(req: LoginBody, db: AsyncSession = Depends(get_db)):
    """兼容前端 /api/login，内部转发到 auth 登录逻辑。"""
    from app.core.auth import create_access_token, verify_password

    user = (
        await db.execute(select(User).where(User.username == req.username))
    ).scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "nickname": user.nickname},
    }


@router.get("/me")
async def compat_me(user: User | None = Depends(get_user_dev)):
    if not user:
        raise HTTPException(401, "未登录")
    return {"id": user.id, "username": user.username, "nickname": user.nickname}


# ---------- 仪表盘 ----------
@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """仪表盘统计：我的小说、总章节、总字数、角色数量。"""
    if not user:
        return {"books": 0, "chapters": 0, "words": "0", "characters": 0}
    books = (
        await db.execute(select(func.count(Project.id)).where(Project.user_id == user.id))
    ).scalar() or 0
    pids = [
        p
        for p in (await db.execute(select(Project.id).where(Project.user_id == user.id)))
        .scalars()
        .all()
    ]
    chapters = words = characters = 0
    if pids:
        chapters = (
            await db.execute(select(func.count(Chapter.id)).where(Chapter.project_id.in_(pids)))
        ).scalar() or 0
        words = (
            await db.execute(
                select(func.coalesce(func.sum(Chapter.word_count), 0)).where(
                    Chapter.project_id.in_(pids)
                )
            )
        ).scalar() or 0
        characters = (
            await db.execute(select(func.count(Character.id)).where(Character.project_id.in_(pids)))
        ).scalar() or 0
    return {"books": books, "chapters": chapters, "words": f"{words:,}", "characters": characters}


async def _recent_activities(db: AsyncSession, user: User, limit: int = 5):
    """最近章节更新 → 前端 Activity 列表。"""
    if not user:
        return []
    rows = (
        await db.execute(
            select(Chapter, Project.title.label("project_title"))
            .join(Project, Project.id == Chapter.project_id)
            .where(Project.user_id == user.id)
            .order_by(Chapter.updated_at.desc().nullslast(), Chapter.id.desc())
            .limit(limit)
        )
    ).all()
    now = datetime.utcnow()
    result = []
    for c, project_title in rows:
        ts = c.updated_at or c.created_at or now
        delta = now - ts
        if delta < timedelta(hours=1):
            meta = f"{c.word_count or 0} 字 · 刚刚"
        elif delta < timedelta(days=1):
            meta = f"{c.word_count or 0} 字 · {delta.seconds // 3600} 小时前"
        else:
            meta = f"{c.word_count or 0} 字 · {delta.days} 天前"
        result.append(
            {
                "title": f"第 {c.chapter_number} 章 · {c.title or '无标题'}",
                "meta": meta,
                "badge": c.status or "草稿",
                "type": _badge_for(c.status),
            }
        )
    return result


@router.get("/recent-edits")
async def recent_edits(
    db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)
):
    return await _recent_activities(db, user, 5)


@router.get("/recent-activity")
async def recent_activity(
    db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)
):
    return await _recent_activities(db, user, 5)


# ---------- 书架（= 项目列表） ----------
@router.get("/books")
async def books(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """前端"我的书架" → 用户所有项目。"""
    if not user:
        return []
    projects = (
        (
            await db.execute(
                select(Project)
                .where(Project.user_id == user.id)
                .order_by(Project.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    items = []
    for p in projects:
        ch_count = (
            await db.execute(select(func.count(Chapter.id)).where(Chapter.project_id == p.id))
        ).scalar() or 0
        words = (
            await db.execute(
                select(func.coalesce(func.sum(Chapter.word_count), 0)).where(
                    Chapter.project_id == p.id
                )
            )
        ).scalar() or 0
        items.append(
            {
                "id": p.id,
                "title": p.title,
                "cover": p.cover_url or "",
                "desc": p.synopsis or "暂无简介",
                "chapters": ch_count,
                "words": f"{words:,}",
                "updated": (p.updated_at or p.created_at).strftime("%Y-%m-%d")
                if (p.updated_at or p.created_at)
                else "",
                "tag": p.genre or "其他",
                "type": _badge_for(p.status),
            }
        )
    return items


class BookCreate(BaseModel):
    title: str
    genre: str = ""
    synopsis: str = ""


@router.post("/books")
async def create_book(
    req: BookCreate, db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)
):
    """新建书（项目）。"""
    if not user:
        raise HTTPException(401, "请先登录")
    p = Project(user_id=user.id, title=req.title, genre=req.genre, synopsis=req.synopsis)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "title": p.title}


# ---------- 当前项目下的章节/大纲/角色/世界观 ----------
@router.get("/chapters")
async def chapters(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """前端"故事章节"页 → 当前项目的章节。"""
    proj = await _current_project(db, user)
    if not proj:
        return []
    rows = (
        (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == proj.id)
                .order_by(Chapter.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.utcnow()
    items = []
    for c in rows:
        ts = c.updated_at or c.created_at
        updated = "—"
        if ts:
            delta = now - ts
            if delta < timedelta(hours=1):
                updated = "刚刚"
            elif delta < timedelta(days=1):
                updated = f"{delta.seconds // 3600} 小时前"
            else:
                updated = f"{delta.days} 天前"
        items.append(
            {
                "id": c.id,
                "no": c.chapter_number,
                "title": c.title or "无标题",
                "words": c.word_count or 0,
                "updated": updated,
                "status": c.status or "草稿",
                "type": _badge_for(c.status),
            }
        )
    return items


@router.get("/outline")
async def outline(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """前端"故事大纲"页 → 当前项目的大纲。"""
    proj = await _current_project(db, user)
    if not proj:
        return []
    rows = (
        (
            await db.execute(
                select(Outline)
                .where(Outline.project_id == proj.id)
                .order_by(Outline.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": o.id,
            "no": o.chapter_number,
            "title": o.title or "无标题",
            "summary": o.summary or "",
            "status": "已规划",
            "type": "info" if o.key_points else "primary",
        }
        for o in rows
    ]


@router.get("/characters")
async def characters(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """前端"角色设定"页 → 当前项目的角色。"""
    proj = await _current_project(db, user)
    if not proj:
        return []
    rows = (
        (await db.execute(select(Character).where(Character.project_id == proj.id))).scalars().all()
    )
    items = []
    for c in rows:
        desc = c.personality or c.background or c.personality or c.background or "暂无描述"
        tags = []
        if c.gender:
            tags.append(c.gender)
        if c.age:
            tags.append(c.age)
        if c.ability:
            tags.append(c.ability)
        items.append(
            {
                "id": c.id,
                "name": c.name,
                "initial": (c.name or "?")[0],
                "role": c.role or "配角",
                "desc": desc,
                "tags": tags[:3],
            }
        )
    return items


@router.get("/worldview")
async def worldview(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """前端"世界设定"页 → 按 category 分组返回。"""
    proj = await _current_project(db, user)
    if not proj:
        return []
    rows = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == proj.id)))
        .scalars()
        .all()
    )
    # 按 category 聚合成 section
    groups: dict[str, list[str]] = {}
    for w in rows:
        key = w.category or "其他"
        groups.setdefault(key, []).append(f"{w.name}：{(w.content or '')[:60]}")
    return [{"title": k, "items": v} for k, v in groups.items()]


# ---------- 写作风格 ----------
# 已迁移到 writing_styles_router（真实数据 + CRUD），此处不再提供假数据兼容
# ---------- 提示词 ----------
@router.get("/prompts")
async def prompts(db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)):
    """提示词模板列表。"""
    base_q = select(PromptTemplate)
    if user:
        rows = (
            (
                await db.execute(
                    base_q.where(
                        (PromptTemplate.user_id == user.id) | (PromptTemplate.user_id.is_(None))
                    )
                )
            )
            .scalars()
            .all()
        )
    else:
        rows = (await db.execute(base_q.where(PromptTemplate.user_id.is_(None)))).scalars().all()
    return [
        {
            "title": p.name,
            "category": p.category or "通用",
            "preview": (p.description or "")[:80],
            "usage": 0,
        }
        for p in rows
    ]


# NOTE: AI 模型和 Skills 的路由已迁移到 global_routes.py
# 此处不再重复定义 /api/ai-models 和 /api/skills，避免路由冲突


# ---------- 写作日志（基于生成历史） ----------
@router.get("/writing-log")
async def writing_log(
    db: AsyncSession = Depends(get_db), user: User | None = Depends(get_user_dev)
):
    """写作日志：基于 GenerationHistory。"""
    if not user:
        return []
    pids = [
        p
        for p in (await db.execute(select(Project.id).where(Project.user_id == user.id)))
        .scalars()
        .all()
    ]
    if not pids:
        return []
    rows = (
        (
            await db.execute(
                select(GenerationHistory)
                .where(GenerationHistory.project_id.in_(pids))
                .order_by(GenerationHistory.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    items = []
    for h in rows:
        ts = h.created_at
        date = ts.strftime("%Y-%m-%d %H:%M") if ts else "—"
        event = f"{h.prompt_name or '生成'} · {h.model_used or '?'}"
        if h.input_tokens or h.output_tokens:
            event += f" · {h.input_tokens or 0}/{h.output_tokens or 0} tokens"
        items.append(
            {
                "date": date,
                "event": event,
                "type": _badge_for(h.status),
            }
        )
    return items


# ---------- MCP 服务器（后端暂未实现，返回空 + 占位） ----------
@router.get("/mcp-servers")
async def mcp_servers():
    """MCP 服务器管理（后端暂无实现，返回空列表占位）。"""
    return []


# ---------- 导入书籍（拆书） ----------
@router.get("/imported-books")
async def imported_books(db: AsyncSession = Depends(get_db), user: User = Depends(get_user_dev)):
    """拆书导入列表：返回当前用户的已导入书籍（按时间倒序）。

    字段对齐前端期望：{id, title, chapters, updated, tag, ...}。
    """
    from app.models.imported_book import ImportedBook

    if not user:
        return []
    rows = (
        (
            await db.execute(
                select(ImportedBook)
                .where(ImportedBook.user_id == user.id)
                .order_by(ImportedBook.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    items = []
    for b in rows:
        d = b.to_dict()
        d["chapters"] = d.get("total_chapters", 0)
        d["updated"] = (d.get("updated_at") or d.get("created_at") or "")[:16].replace("T", " ")
        d["tag"] = "已拆解" if b.status == "project_created" else "待拆解"
        items.append(d)
    return items


# ---------- AI 对话历史（后端暂未实现，返回空 + 占位） ----------
@router.get("/chat-history")
async def chat_history():
    """AI 对话历史（后端暂无实现，返回空列表占位）。"""
    return []
