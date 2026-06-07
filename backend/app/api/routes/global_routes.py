"""全局路由（不依赖项目 ID 的用户级接口）

本模块承载"用户级"而非"项目级"的接口，包括：
- AI 模型配置（CRUD + 测试 + 拉取远程模型）
- Skill 管理（列表/更新/重置/自定义创建/删除）
- 全局灵感模式（无需先建项目）

将这些接口从 projects.py 分离出来的原因：
1. 语义清晰：它们不依赖某个具体项目，不应挂在 /api/projects 下
2. 避免路由冲突：projects.py 中 /{project_id} 动态路由会捕获
   /api/projects/ai-models 等静态路径（"ai-models" 无法转 int → 422）
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_client import AIClient
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.skills.engine import SkillEngine

router = APIRouter(prefix="/api", tags=["全局接口"])


# ===========================================================================
# AI 模型配置
# ===========================================================================
class AIModelCreate(BaseModel):
    name: str = "默认"
    base_url: str = ""
    api_key: str = ""
    model: str
    temperature: int = 85
    top_p: int = 90
    max_tokens: int = 4096
    is_default: bool = False
    backend_type: str = "openai"
    provider: str = "openai"
    embedding_model: str = ""


class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[int] = None
    top_p: Optional[int] = None
    max_tokens: Optional[int] = None
    is_default: Optional[bool] = None
    backend_type: Optional[str] = None
    provider: Optional[str] = None
    embedding_model: Optional[str] = None


@router.get("/ai-models")
async def list_ai_models(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """列出当前用户所有 AI 模型配置。"""
    from app.models.ai_model import AIModelConfig

    result = await db.execute(select(AIModelConfig).where(AIModelConfig.user_id == user.id))
    models = result.scalars().all()
    return [{
        "id": m.id, "name": m.name, "base_url": m.base_url, "model": m.model,
        "temperature": m.temperature, "top_p": m.top_p, "max_tokens": m.max_tokens,
        "is_default": m.is_default, "backend_type": m.backend_type or "openai",
        "provider": m.provider or m.backend_type or "openai",
        "embedding_model": m.embedding_model or "",
        "created_at": m.created_at.isoformat() if m.created_at else "",
    } for m in models]


@router.post("/ai-models")
async def create_ai_model(req: AIModelCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """新建 AI 模型配置。"""
    from app.models.ai_model import AIModelConfig

    if req.is_default:
        result = await db.execute(
            select(AIModelConfig).where(AIModelConfig.user_id == user.id, AIModelConfig.is_default == True)
        )
        for m in result.scalars().all():
            m.is_default = False
    model = AIModelConfig(user_id=user.id, **req.model_dump())
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return {"id": model.id, "name": model.name}


@router.put("/ai-models/{model_id}")
async def update_ai_model(model_id: int, req: AIModelUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """更新 AI 模型配置。"""
    from app.models.ai_model import AIModelConfig

    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.id == model_id, AIModelConfig.user_id == user.id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "模型配置不存在")
    data = req.model_dump(exclude_none=True)
    if data.get("is_default"):
        others = await db.execute(
            select(AIModelConfig).where(
                AIModelConfig.user_id == user.id,
                AIModelConfig.is_default == True,
                AIModelConfig.id != model_id,
            )
        )
        for o in others.scalars().all():
            o.is_default = False
    for k, v in data.items():
        setattr(m, k, v)
    await db.commit()
    return {"ok": True}


@router.delete("/ai-models/{model_id}")
async def delete_ai_model(model_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除 AI 模型配置。"""
    from app.models.ai_model import AIModelConfig

    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.id == model_id, AIModelConfig.user_id == user.id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "模型配置不存在")
    await db.delete(m)
    await db.commit()
    return {"ok": True}


@router.post("/ai-models/{model_id}/test")
async def test_ai_model(model_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """测试 AI 模型连通性。"""
    from app.models.ai_model import AIModelConfig

    result = await db.execute(
        select(AIModelConfig).where(AIModelConfig.id == model_id, AIModelConfig.user_id == user.id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(404, "模型配置不存在")
    client = AIClient(base_url=m.base_url, api_key=m.api_key, model=m.model)
    resp = await client.chat(
        messages=[{"role": "user", "content": "请回复：连接成功"}],
        max_tokens=20,
    )
    if resp.get("error"):
        raise HTTPException(400, f"连接失败: {resp['error']}")
    return {"ok": True, "reply": resp["content"][:50], "model": resp["model"]}


# ---- AI 模型：从远程获取可用模型列表 ----
class FetchModelsReq(BaseModel):
    base_url: str
    api_key: str
    provider: str = "openai"


@router.post("/ai-models/fetch-remote")
async def fetch_remote_models(req: FetchModelsReq, user=Depends(get_current_user)):
    """根据 base_url/api_key/provider 获取远程可用模型列表。

    - openai（兼容）: GET {base}/v1/models 或 {base}/models
    - gemini: GET {base}/models?key={api_key}
    - anthropic: 官方无公开列表接口，返回提示
    """
    import httpx

    base = req.base_url.rstrip("/")
    provider = (req.provider or "openai").lower()

    # 确定 URL
    if provider == "gemini":
        url = f"{base}/models?key={req.api_key}"
    else:
        # openai 兼容：兼容 {base}/v1 和 {base} 两种
        if base.endswith("/v1"):
            url = f"{base}/models"
        else:
            url = f"{base}/v1/models" if "/v1" not in base else f"{base}/models"
        # 兜底：若 /v1/models 失败再试 /models
    headers = {"Authorization": f"Bearer {req.api_key}"} if provider != "gemini" else {}

    urls_to_try = [url]
    # openai 兼容做兜底
    if provider == "openai":
        alt = url.replace("/v1/models", "/models") if "/v1/models" in url else url.replace("/models", "/v1/models")
        if alt not in urls_to_try:
            urls_to_try.append(alt)

    last_err = ""
    async with httpx.AsyncClient(timeout=15.0) as client:
        for try_url in urls_to_try:
            try:
                resp = await client.get(try_url, headers=headers)
                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    continue
                data = resp.json()
                # Gemini 格式：{models:[{name:"models/gemini-1.5-flash",...}]}
                if provider == "gemini":
                    raw = data.get("models", [])
                    models = [{
                        "id": m.get("name", "").replace("models/", ""),
                        "owned_by": "google",
                        "supported": m.get("supportedGenerationMethods", []),
                    } for m in raw]
                else:
                    raw = data.get("data", [])
                    models = [{"id": m.get("id", ""), "owned_by": m.get("owned_by", "")} for m in raw]
                models.sort(key=lambda m: m.get("id", ""))
                return {"models": models}
            except httpx.ConnectError:
                last_err = "无法连接到服务器，请检查 Base URL"
            except httpx.TimeoutException:
                last_err = "连接超时"
            except Exception as e:
                last_err = str(e)
    raise HTTPException(400, last_err or "获取模型列表失败")


class TestEmbeddingReq(BaseModel):
    base_url: str
    api_key: str
    embedding_model: str = "text-embedding-3-small"


@router.post("/ai-models/test-embedding")
async def test_embedding(req: TestEmbeddingReq, user=Depends(get_current_user)):
    """测试 embedding 接口连通性（用于记忆向量检索配置）。"""
    client = AIClient(
        base_url=req.base_url,
        api_key=req.api_key,
        embedding_model=req.embedding_model,
    )
    r = await client.embed("测试文本")
    if r.get("error"):
        raise HTTPException(400, f"Embedding 失败: {r['error']}")
    dim = len(r["vectors"][0]) if r.get("vectors") else 0
    return {"ok": True, "dim": dim, "model": r["model"], "count": r["count"]}


# ===========================================================================
# Skill 管理（用户级配置）
# ===========================================================================
class SkillCreateReq(BaseModel):
    name: str
    display_name: str = ""
    description: str = ""
    category: str = "custom"
    system_prompt: str


class SkillUpdateReq(BaseModel):
    system_prompt: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[dict] = None


@router.get("/skills")
async def list_skills(category: str = None, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """列出所有 Skill（含用户级配置覆盖）。"""
    from app.models.skill import Skill

    q = select(Skill)
    if category:
        q = q.where(Skill.category == category)
    q = q.order_by(Skill.category, Skill.id)
    result = await db.execute(q)
    skills = list(result.scalars().all())
    engine = SkillEngine(db, user.id)
    out = []
    for s in skills:
        user_cfg = await engine.get_user_config(s.id)
        out.append({
            "id": s.id,
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "category": s.category,
            "skill_type": s.skill_type,
            "is_enabled": user_cfg["is_enabled"] if user_cfg else s.is_enabled,
            "system_prompt": (
                (user_cfg.get("config", {}) or {}).get("system_prompt")
                if user_cfg and user_cfg.get("config")
                else s.system_prompt
            ),
            "parameters": s.parameters,
            "config": s.config,
        })
    return out


@router.put("/skills/{skill_id}")
async def update_skill(skill_id: int, req: SkillUpdateReq, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """更新 Skill（用户级配置覆盖，不影响系统默认）。"""
    from app.models.skill import Skill, SkillConfig

    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "Skill 不存在")
    cfg_result = await db.execute(
        select(SkillConfig).where(SkillConfig.skill_id == skill_id, SkillConfig.user_id == user.id)
    )
    cfg = cfg_result.scalar_one_or_none()
    if not cfg:
        cfg = SkillConfig(skill_id=skill_id, user_id=user.id, is_enabled=True, config={})
        db.add(cfg)
    if req.is_enabled is not None:
        cfg.is_enabled = req.is_enabled
    if req.system_prompt is not None:
        merged = dict(cfg.config or {})
        merged["system_prompt"] = req.system_prompt
        cfg.config = merged
    if req.config is not None:
        cfg.config = {**(cfg.config or {}), **req.config}
    await db.commit()
    return {"ok": True}


@router.post("/skills/{skill_id}/reset")
async def reset_skill(skill_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """重置 Skill 到系统默认（删除用户级覆盖配置）。"""
    from app.models.skill import SkillConfig

    result = await db.execute(
        select(SkillConfig).where(SkillConfig.skill_id == skill_id, SkillConfig.user_id == user.id)
    )
    cfg = result.scalar_one_or_none()
    if cfg:
        await db.delete(cfg)
        await db.commit()
    return {"ok": True}


@router.post("/skills/create")
async def create_custom_skill(req: SkillCreateReq, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """用户自定义创建 Skill（可通过粘贴 MD 内容安装）。"""
    from app.models.skill import Skill

    slug = req.name.lower().replace(" ", "_").replace("-", "_")
    result = await db.execute(select(Skill).where(Skill.name == slug))
    if result.scalar_one_or_none():
        raise HTTPException(400, f"Skill '{slug}' 已存在")
    skill = Skill(
        name=slug,
        display_name=req.display_name or req.name,
        description=req.description,
        category=req.category,
        skill_type="custom",
        system_prompt=req.system_prompt,
        is_enabled=True,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return {"ok": True, "id": skill.id, "name": skill.name}


@router.delete("/skills/{skill_id}/custom")
async def delete_custom_skill(skill_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除用户自定义 Skill（仅 skill_type=custom 可删除）。"""
    from app.models.skill import Skill

    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(404, "Skill 不存在")
    if skill.skill_type != "custom":
        raise HTTPException(400, "内置 Skill 不可删除")
    await db.delete(skill)
    await db.commit()
    return {"ok": True}


# ===========================================================================
# 全局灵感模式（无需先建项目）
# ===========================================================================
class InspireRequest(BaseModel):
    idea: str


@router.post("/global-inspire")
async def global_inspire(req: InspireRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """全局灵感：从一个想法拓展为完整创作方案，并可选直接建项目。"""
    engine = SkillEngine(db, user.id)
    ai_client = await AIClient.from_user_config(db, user.id)
    result = await engine.execute_skill("inspire", ai_client, {
        "idea": req.idea,
        "user_prompt": f"我的想法是：{req.idea}，请帮我拓展成创作方案。",
    })
    if result.get("error"):
        raise HTTPException(500, result["error"])
    return result.get("json") or {}