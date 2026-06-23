"""写作风格管理：预设/CRUD/设为项目默认。

对标 MuMuAINovel writing_styles API。功能等价版。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.writing_style import WritingStyle
from app.models.project import Project

router = APIRouter(prefix="/api/writing-styles", tags=["写作风格"])


class StyleCreate(BaseModel):
    name: str
    description: str = ""
    config: dict = {}
    custom_prompt: str = ""


class StyleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None
    custom_prompt: Optional[str] = None


# 内置风格预设（对标原项目的 init-defaults）
BUILTIN_PRESETS = [
    {"name": "快节奏爽文", "description": "节奏明快，爽点密集，适合升级流", "config": {"pacing": "快", "tone": "热血", "sentence_length": "短句为主", "description_focus": "动作", "dialogue_ratio": "中等"}},
    {"name": "细腻文艺", "description": "注重心理描写和环境渲染，文笔细腻", "config": {"pacing": "慢", "tone": "沉静", "sentence_length": "长短结合", "description_focus": "心理", "dialogue_ratio": "低"}},
    {"name": "幽默轻松", "description": "轻松诙谐，对话多，适合日常向", "config": {"pacing": "中", "tone": "幽默", "sentence_length": "短句", "description_focus": "对话", "dialogue_ratio": "高"}},
    {"name": "悬疑烧脑", "description": "层层悬念，信息克制，适合推理悬疑", "config": {"pacing": "中", "tone": "紧张", "sentence_length": "多变", "description_focus": "线索", "dialogue_ratio": "中等"}},
    {"name": "史诗厚重", "description": "宏大叙事，细节丰富，适合奇幻历史", "config": {"pacing": "慢", "tone": "庄重", "sentence_length": "长句为主", "description_focus": "环境", "dialogue_ratio": "低"}},
]


async def ensure_presets(db: AsyncSession, user_id: int):
    """首次使用时为用户种入内置预设"""
    existing = (await db.execute(select(WritingStyle).where(WritingStyle.user_id == user_id, WritingStyle.is_preset == True))).scalars().all()
    if existing:
        return
    for preset in BUILTIN_PRESETS:
        db.add(WritingStyle(user_id=user_id, is_preset=True, **preset))
    await db.commit()


@router.get("")
async def list_styles(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """列出当前用户的所有风格（含内置预设）"""
    await ensure_presets(db, user.id)
    result = await db.execute(select(WritingStyle).where(WritingStyle.user_id == user.id).order_by(WritingStyle.is_preset.desc()))
    return [s.to_dict() for s in result.scalars().all()]


@router.post("")
async def create_style(req: StyleCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    style = WritingStyle(user_id=user.id, name=req.name, description=req.description,
                         config=req.config, custom_prompt=req.custom_prompt)
    db.add(style)
    await db.commit()
    await db.refresh(style)
    return style.to_dict()


@router.put("/{style_id}")
async def update_style(style_id: int, req: StyleUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    s = (await db.execute(select(WritingStyle).where(WritingStyle.id == style_id, WritingStyle.user_id == user.id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "风格不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    return {"ok": True}


@router.delete("/{style_id}")
async def delete_style(style_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    s = (await db.execute(select(WritingStyle).where(WritingStyle.id == style_id, WritingStyle.user_id == user.id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "风格不存在")
    if s.is_preset:
        raise HTTPException(400, "内置预设不可删除")
    await db.delete(s)
    await db.commit()
    return {"ok": True}


@router.post("/{style_id}/apply/{project_id}")
async def apply_to_project(style_id: int, project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """将风格设为项目的默认写作风格（写入 project.writing_style）"""
    style = (await db.execute(select(WritingStyle).where(WritingStyle.id == style_id, WritingStyle.user_id == user.id))).scalar_one_or_none()
    if not style:
        raise HTTPException(404, "风格不存在")
    proj = (await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "项目不存在")
    proj.writing_style = {
        "name": style.name, "description": style.description,
        "custom_prompt": style.custom_prompt or "",
        **(style.config or {}),
    }
    await db.commit()
    return {"ok": True, "project_id": project_id, "style_name": style.name}
