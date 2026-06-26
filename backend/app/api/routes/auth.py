"""认证路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from app.core.database import get_db
from app.core.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    nickname: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise HTTPException(400, "用户名已存在")
    # 第一个注册的用户自动成为管理员
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    is_first_user = user_count == 0
    user = User(
        username=req.username,
        password_hash=get_password_hash(req.password),
        nickname=req.nickname or req.username,
        is_admin=is_first_user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "username": user.username, "nickname": user.nickname, "is_admin": user.is_admin},
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user={"id": user.id, "username": user.username, "nickname": user.nickname, "is_admin": user.is_admin},
    )


@router.get("/me")
async def get_me(user=Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "nickname": user.nickname, "is_admin": user.is_admin, "settings": user.settings}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码：验证旧密码后更新为新密码。"""
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(400, "旧密码错误")
    if len(req.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 个字符")
    user.password_hash = get_password_hash(req.new_password)
    await db.commit()
    return {"ok": True, "message": "密码修改成功"}