"""PromptTemplate 版本管理路由"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.prompt_template import PromptTemplate, PromptVersion

router = APIRouter(prefix="/api/prompt-templates", tags=["提示词模板"])


async def _sync_version_to_skill(db: AsyncSession, template_name: str, system_prompt: str):
    """将激活版本的 system_prompt 同步到 skills 表，使运行时生效。"""
    from app.models.skill import Skill
    skill_name = template_name.lower()
    result = await db.execute(select(Skill).where(Skill.name == skill_name))
    skill = result.scalar_one_or_none()
    if skill and system_prompt:
        skill.system_prompt = system_prompt
        await db.flush()


# ---- Pydantic Models ----
class PromptTemplateCreate(BaseModel):
    name: str
    category: str = "custom"
    description: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    variables: list = []
    config: dict = {}


class PromptTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


class PromptVersionCreate(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    variables: list = []
    config: dict = {}


class PromptTemplateBatchImport(BaseModel):
    templates: list[dict]


# ---- 辅助函数 ----
def _template_to_dict(t: PromptTemplate, active_version: PromptVersion = None) -> dict:
    """将 PromptTemplate ORM 对象序列化为字典"""
    # display_name：优先用描述（更友好），回退到 name（name 为大写 skill 名，如 WORLD_CORE_GENERATE）
    display_name = t.description or t.name
    result = {
        "id": t.id,
        "user_id": t.user_id,
        "name": t.name,
        "display_name": display_name,
        "category": t.category,
        "description": t.description,
        "is_system": t.is_system,
        "current_version_id": t.current_version_id,
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
    }
    if active_version:
        result["system_prompt"] = active_version.system_prompt
        result["user_prompt"] = active_version.user_prompt
        result["variables"] = active_version.variables
        result["config"] = active_version.config
    return result


def _version_to_dict(v: PromptVersion) -> dict:
    """将 PromptVersion ORM 对象序列化为字典"""
    return {
        "id": v.id,
        "template_id": v.template_id,
        "version": v.version,
        "system_prompt": v.system_prompt,
        "user_prompt": v.user_prompt,
        "variables": v.variables,
        "config": v.config,
        "is_active": v.is_active,
        "created_at": v.created_at.isoformat() if v.created_at else "",
    }


# ---- 模板 CRUD ----
@router.get("")
async def list_templates(
    category: str = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """列出模板（支持 ?category= 筛选）"""
    q = select(PromptTemplate)
    if category:
        q = q.where(PromptTemplate.category == category)
    q = q.order_by(PromptTemplate.category, PromptTemplate.id)
    result = await db.execute(q)
    templates = result.scalars().all()

    items = []
    for t in templates:
        # 获取当前激活版本的内容
        active_version = None
        if t.current_version_id:
            ver_result = await db.execute(
                select(PromptVersion).where(PromptVersion.id == t.current_version_id)
            )
            active_version = ver_result.scalar_one_or_none()
        # 兜底：若没有激活版本或 system_prompt 为空，从 Skill 表回填（系统模板可能未同步 PromptVersion）
        if not active_version or not (active_version.system_prompt or "").strip():
            from app.models.skill import Skill
            skill = (await db.execute(
                select(Skill).where(Skill.name == t.name)
            )).scalar_one_or_none()
            if skill and (skill.system_prompt or "").strip():
                # 用一个轻量占位 version 对象回填，不改库
                if not active_version:
                    active_version = PromptVersion(
                        template_id=t.id, version=1,
                        system_prompt=skill.system_prompt,
                        user_prompt="", variables=skill.parameters or {},
                        config={}, is_active=True,
                    )
                else:
                    if not (active_version.system_prompt or "").strip():
                        active_version.system_prompt = skill.system_prompt
        items.append(_template_to_dict(t, active_version))
    return items


@router.post("")
async def create_template(
    req: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建自定义模板（自动创建 version=1 并设为激活）"""
    template = PromptTemplate(
        user_id=user.id,
        name=req.name,
        category=req.category,
        description=req.description,
        is_system=False,
    )
    db.add(template)
    await db.flush()  # 获取 template.id

    version = PromptVersion(
        template_id=template.id,
        version=1,
        system_prompt=req.system_prompt,
        user_prompt=req.user_prompt,
        variables=req.variables,
        config=req.config,
        is_active=True,
    )
    db.add(version)
    await db.flush()  # 获取 version.id

    template.current_version_id = version.id
    await db.commit()
    await db.refresh(template)

    return {
        "id": template.id,
        "name": template.name,
        "version_id": version.id,
    }


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除模板（仅非系统模板可删）"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "模板不存在")
    if template.is_system:
        raise HTTPException(400, "系统模板不可删除")

    # 先删除所有版本
    ver_result = await db.execute(
        select(PromptVersion).where(PromptVersion.template_id == template_id)
    )
    for v in ver_result.scalars().all():
        await db.delete(v)

    await db.delete(template)
    await db.commit()
    return {"ok": True}


# ---- 版本管理 ----
@router.get("/{template_id}/versions")
async def list_versions(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """列出某模板的所有版本"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "模板不存在")

    ver_result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.template_id == template_id)
        .order_by(PromptVersion.version.desc())
    )
    versions = ver_result.scalars().all()
    return [_version_to_dict(v) for v in versions]


@router.post("/{template_id}/versions")
async def create_version(
    template_id: int,
    req: PromptVersionCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """创建新版本（自增 version 号）"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "模板不存在")

    # 获取当前最大版本号
    max_result = await db.execute(
        select(func.max(PromptVersion.version)).where(
            PromptVersion.template_id == template_id
        )
    )
    max_version = max_result.scalar() or 0
    new_version_num = max_version + 1

    # 将旧版本全部设为非激活
    old_versions = await db.execute(
        select(PromptVersion).where(
            PromptVersion.template_id == template_id,
            PromptVersion.is_active == True,
        )
    )
    for v in old_versions.scalars().all():
        v.is_active = False

    version = PromptVersion(
        template_id=template_id,
        version=new_version_num,
        system_prompt=req.system_prompt,
        user_prompt=req.user_prompt,
        variables=req.variables,
        config=req.config,
        is_active=True,
    )
    db.add(version)
    await db.flush()

    template.current_version_id = version.id
    await db.commit()
    await db.refresh(version)

    return {
        "id": version.id,
        "version": version.version,
        "is_active": version.is_active,
    }


@router.post("/{template_id}/activate/{version_id}")
async def activate_version(
    template_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """激活指定版本"""
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.id == template_id)
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(404, "模板不存在")

    # 检查目标版本是否属于该模板
    ver_result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.id == version_id,
            PromptVersion.template_id == template_id,
        )
    )
    target_version = ver_result.scalar_one_or_none()
    if not target_version:
        raise HTTPException(404, "版本不存在")

    # 将该模板下所有版本设为非激活
    all_versions = await db.execute(
        select(PromptVersion).where(PromptVersion.template_id == template_id)
    )
    for v in all_versions.scalars().all():
        v.is_active = False

    # 激活目标版本
    target_version.is_active = True
    template.current_version_id = target_version.id

    # 同步到 skills 表：让运行时 SkillEngine 使用这个版本的 prompt
    await _sync_version_to_skill(db, template.name, target_version.system_prompt)

    await db.commit()

    return {"ok": True, "active_version_id": target_version.id}


# ---- 批量导入 ----
@router.post("/import")
async def batch_import(
    req: PromptTemplateBatchImport,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从 JSON 批量导入模板"""
    imported = 0
    skipped = 0

    for tpl in req.templates:
        name = tpl.get("name") or tpl.get("template_key", "")
        if not name:
            skipped += 1
            continue

        category = tpl.get("category", "custom")
        description = tpl.get("description", "") or tpl.get("template_name", "")
        system_prompt = tpl.get("system_prompt", "") or tpl.get("template_content", "")
        user_prompt = tpl.get("user_prompt", "")
        variables = tpl.get("variables", [])
        if isinstance(variables, str):
            try:
                variables = json.loads(variables)
            except (json.JSONDecodeError, TypeError):
                variables = []
        config = tpl.get("config", {})

        # 幂等：同名则更新内容
        existing_result = await db.execute(
            select(PromptTemplate).where(PromptTemplate.name == name)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # 更新已有模板的描述字段
            if description:
                existing.description = description
            if category:
                existing.category = category
            # 更新当前激活版本的内容
            if existing.current_version_id:
                ver_result = await db.execute(
                    select(PromptVersion).where(
                        PromptVersion.id == existing.current_version_id
                    )
                )
                active_ver = ver_result.scalar_one_or_none()
                if active_ver:
                    active_ver.system_prompt = system_prompt
                    active_ver.user_prompt = user_prompt
                    active_ver.variables = variables
                    active_ver.config = config
            imported += 1
        else:
            template = PromptTemplate(
                user_id=user.id,
                name=name,
                category=category,
                description=description,
                is_system=False,
            )
            db.add(template)
            await db.flush()

            version = PromptVersion(
                template_id=template.id,
                version=1,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                variables=variables,
                config=config,
                is_active=True,
            )
            db.add(version)
            await db.flush()

            template.current_version_id = version.id
            imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped}
