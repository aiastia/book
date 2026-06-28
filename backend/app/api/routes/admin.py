"""管理员后台路由（#4 用户管理 + #5 系统设置 SMTP）。

对标 MuMuAINovel admin.py + settings.py（系统级部分）。
所有端点需 is_admin 校验。
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, get_password_hash
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


# ===== 权限校验依赖 =====
async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(403, "需要管理员权限")
    return user


def _user_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email or "",
        "nickname": u.nickname or "",
        "avatar_url": u.avatar_url or "",
        "is_active": u.is_active,
        "is_admin": u.is_admin,
        "oauth_provider": u.oauth_provider,
        "created_at": u.created_at.isoformat() if u.created_at else "",
    }


# ===== #4 用户管理 =====
@router.get("/users")
async def list_users(
    keyword: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """用户列表（管理员）。"""
    q = select(User)
    if keyword:
        q = q.where(
            (User.username.like(f"%{keyword}%"))
            | (User.email.like(f"%{keyword}%"))
            | (User.nickname.like(f"%{keyword}%"))
        )
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    q = q.order_by(User.id.asc()).offset((page - 1) * page_size).limit(page_size)
    users = (await db.execute(q)).scalars().all()
    return {
        "items": [_user_dict(u) for u in users],
        "total": total or 0,
        "page": page,
        "page_size": page_size,
    }


class CreateUserReq(BaseModel):
    username: str
    password: str = ""
    email: str = ""
    nickname: str = ""
    is_admin: bool = False


@router.post("/users")
async def create_user(
    req: CreateUserReq,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建用户（管理员）。"""
    existing = (
        await db.execute(select(User).where(User.username == req.username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "用户名已存在")
    pwd = req.password or secrets.token_urlsafe(12)
    user = User(
        username=req.username,
        email=req.email or None,
        nickname=req.nickname or req.username,
        password_hash=get_password_hash(pwd),
        is_active=True,
        is_admin=req.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {**_user_dict(user), "initial_password": pwd}


class UpdateUserReq(BaseModel):
    nickname: str = None
    email: str = None
    is_active: bool = None
    is_admin: bool = None


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    req: UpdateUserReq,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新用户信息（管理员）。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    # 保护：不能禁用/降级自己
    if admin.id == user_id and req.is_admin is False:
        raise HTTPException(400, "不能取消自己的管理员权限")
    if admin.id == user_id and req.is_active is False:
        raise HTTPException(400, "不能禁用自己的账号")
    # 保护：不能取消最后一个管理员
    if req.is_admin is False and user.is_admin:
        admin_count = await db.scalar(select(func.count(User.id)).where(User.is_admin == True))
        if admin_count <= 1:
            raise HTTPException(400, "系统至少需要保留一个管理员")
    for k in ["nickname", "email", "is_active", "is_admin"]:
        v = getattr(req, k)
        if v is not None:
            setattr(user, k, v)
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """重置用户密码（管理员，返回新密码）。"""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    new_pwd = secrets.token_urlsafe(12)
    user.password_hash = get_password_hash(new_pwd)
    await db.commit()
    return {"new_password": new_pwd}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除用户（管理员）。"""
    if admin.id == user_id:
        raise HTTPException(400, "不能删除自己")
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "用户不存在")
    if user.is_admin:
        admin_count = await db.scalar(select(func.count(User.id)).where(User.is_admin == True))
        if admin_count <= 1:
            raise HTTPException(400, "不能删除最后一个管理员")
    await db.delete(user)
    await db.commit()
    return {"ok": True}


@router.get("/stats")
async def admin_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """系统统计（管理员）。"""
    from app.models.chapter import Chapter
    from app.models.project import Project

    user_count = await db.scalar(select(func.count(User.id)))
    project_count = await db.scalar(select(func.count(Project.id)))
    chapter_count = await db.scalar(select(func.count(Chapter.id)))
    admin_count = await db.scalar(select(func.count(User.id)).where(User.is_admin == True))
    active_count = await db.scalar(select(func.count(User.id)).where(User.is_active == True))
    return {
        "users": user_count or 0,
        "admins": admin_count or 0,
        "active_users": active_count or 0,
        "projects": project_count or 0,
        "chapters": chapter_count or 0,
    }


# ===== #5 系统设置 SMTP =====
class SMTPConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    smtp_from_email: str = ""
    smtp_from_name: str = "墨语"
    email_auth_enabled: bool = False  # 是否开启邮箱验证码登录
    email_register_enabled: bool = False  # 是否开启邮箱注册


async def _get_admin_user(db: AsyncSession, admin: User) -> User:
    """系统级配置存在管理员用户的 settings 字段里。"""
    await db.refresh(admin)
    return admin


@router.get("/system/smtp")
async def get_smtp(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取 SMTP 配置（管理员）。"""
    admin_user = await _get_admin_user(db, admin)
    settings = admin_user.settings or {}
    smtp = settings.get("smtp", {})
    # 密码脱敏
    return {
        "smtp_host": smtp.get("smtp_host", ""),
        "smtp_port": smtp.get("smtp_port", 465),
        "smtp_username": smtp.get("smtp_username", ""),
        "smtp_password": "•••••" if smtp.get("smtp_password") else "",
        "smtp_use_ssl": smtp.get("smtp_use_ssl", True),
        "smtp_use_tls": smtp.get("smtp_use_tls", False),
        "smtp_from_email": smtp.get("smtp_from_email", ""),
        "smtp_from_name": smtp.get("smtp_from_name", "墨语"),
        "email_auth_enabled": smtp.get("email_auth_enabled", False),
        "email_register_enabled": smtp.get("email_register_enabled", False),
    }


@router.put("/system/smtp")
async def update_smtp(
    req: SMTPConfig,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新 SMTP 配置（管理员）。"""
    admin_user = await _get_admin_user(db, admin)
    settings = dict(admin_user.settings or {})
    old_smtp = settings.get("smtp", {})
    new_smtp = req.model_dump()
    # 密码：若传入的是占位符则保留旧密码
    if new_smtp["smtp_password"] == "•••••":
        new_smtp["smtp_password"] = old_smtp.get("smtp_password", "")
    settings["smtp"] = new_smtp
    admin_user.settings = settings
    await db.commit()
    return {"ok": True}


class SMTPTestReq(BaseModel):
    to_email: str


@router.post("/system/smtp/test")
async def test_smtp(
    req: SMTPTestReq,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """发送测试邮件（管理员）。"""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    admin_user = await _get_admin_user(db, admin)
    smtp = (admin_user.settings or {}).get("smtp", {})
    host = smtp.get("smtp_host", "")
    port = smtp.get("smtp_port", 465)
    username = smtp.get("smtp_username", "")
    password = smtp.get("smtp_password", "")
    from_email = smtp.get("smtp_from_email", username)
    from_name = smtp.get("smtp_from_name", "墨语")
    use_ssl = smtp.get("smtp_use_ssl", True)

    if not host or not password:
        raise HTTPException(400, "请先配置 SMTP 主机和密码")

    msg = MIMEMultipart()
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = req.to_email
    msg["Subject"] = "墨语 - 测试邮件"
    msg.attach(
        MIMEText("这是一封来自墨语的测试邮件，如果您收到说明 SMTP 配置正确。", "plain", "utf-8")
    )

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if smtp.get("smtp_use_tls"):
                server.starttls()
        server.login(username, password)
        server.sendmail(from_email, [req.to_email], msg.as_string())
        server.quit()
        return {"ok": True, "message": f"测试邮件已发送至 {req.to_email}"}
    except Exception as e:
        raise HTTPException(400, f"发送失败: {str(e)}") from e
