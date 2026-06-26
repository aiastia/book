"""角色职业关联路由（#19）。

承载角色修炼/从事的职业及其阶段进度。与剧情分析联动自动更新。
"""
import logging
from app.api.routes.projects_pkg.base import *
from app.models.character_career import CharacterCareer
from app.models.career import Career
from app.models.character import Character

logger = logging.getLogger(__name__)
router = make_router()


class CharCareerCreateReq(BaseModel):
    character_id: int
    career_id: int
    career_type: str = "main"  # main/sub
    current_stage: int = 1
    stage_progress: int = 0
    started_at: str = ""
    notes: str = ""


@router.get("/{project_id}/character-careers")
async def list_char_careers(
    project_id: int,
    character_id: int = None,
    career_id: int = None,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """列出角色职业关联。"""
    await get_user_project(db, project_id, user)
    q = select(CharacterCareer).where(CharacterCareer.project_id == project_id)
    if character_id:
        q = q.where(CharacterCareer.character_id == character_id)
    if career_id:
        q = q.where(CharacterCareer.career_id == career_id)
    rows = (await db.execute(q)).scalars().all()
    # 关联职业名 + 阶段名
    career_ids = list({r.career_id for r in rows})
    career_map = {}
    if career_ids:
        careers = (await db.execute(select(Career).where(Career.id.in_(career_ids)))).scalars().all()
        for c in careers:
            stages = c.stages or []
            career_map[c.id] = {
                "name": c.name,
                "career_type": c.career_type,
                "max_stage": c.max_stage or len(stages) if isinstance(stages, list) else 10,
                "stages": stages if isinstance(stages, list) else [],
            }
    char_ids = list({r.character_id for r in rows})
    char_map = {}
    if char_ids:
        chars = (await db.execute(select(Character).where(Character.id.in_(char_ids)))).scalars().all()
        char_map = {c.id: c.name for c in chars}
    return [{
        **r.to_dict(),
        "character_name": char_map.get(r.character_id, ""),
        "career_name": career_map.get(r.career_id, {}).get("name", ""),
        "career_max_stage": career_map.get(r.career_id, {}).get("max_stage", 10),
        "stage_name": (career_map.get(r.career_id, {}).get("stages", [])[r.current_stage - 1]
                       if career_map.get(r.career_id, {}).get("stages")
                       and r.current_stage <= len(career_map.get(r.career_id, {}).get("stages", []))
                       else f"第{r.current_stage}阶段"),
    } for r in rows]


@router.post("/{project_id}/character-careers")
async def create_char_career(
    project_id: int, req: CharCareerCreateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """为角色绑定职业。"""
    await get_user_project(db, project_id, user)
    existing = (await db.execute(
        select(CharacterCareer).where(
            CharacterCareer.character_id == req.character_id,
            CharacterCareer.career_id == req.career_id,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "该角色已修炼此职业")
    cc = CharacterCareer(project_id=project_id, source="manual", **req.model_dump())
    db.add(cc)
    await db.commit()
    await db.refresh(cc)
    # 同步角色冗余字段
    char = (await db.execute(select(Character).where(Character.id == req.character_id))).scalar_one_or_none()
    if char:
        if req.career_type == "main":
            char.main_career_id = req.career_id
            char.main_career_stage = req.current_stage
        else:
            subs = char.sub_careers or []
            career = (await db.execute(select(Career).where(Career.id == req.career_id))).scalar_one_or_none()
            subs.append({"career_id": req.career_id, "name": career.name if career else "", "stage": req.current_stage})
            char.sub_careers = subs
        await db.commit()
    return cc.to_dict()


@router.put("/{project_id}/character-careers/{cc_id}")
async def update_char_career(
    project_id: int, cc_id: int, req: dict,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    cc = (await db.execute(
        select(CharacterCareer).where(CharacterCareer.id == cc_id, CharacterCareer.project_id == project_id)
    )).scalar_one_or_none()
    if not cc:
        raise HTTPException(404, "关联记录不存在")
    for k in ["career_type", "current_stage", "stage_progress", "started_at", "reached_current_stage_at", "notes"]:
        if k in req:
            setattr(cc, k, req[k])
    await db.commit()
    # 同步角色冗余
    if cc.career_type == "main":
        char = (await db.execute(select(Character).where(Character.id == cc.character_id))).scalar_one_or_none()
        if char:
            char.main_career_stage = cc.current_stage
            await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/character-careers/{cc_id}")
async def delete_char_career(
    project_id: int, cc_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    cc = (await db.execute(
        select(CharacterCareer).where(CharacterCareer.id == cc_id, CharacterCareer.project_id == project_id)
    )).scalar_one_or_none()
    if not cc:
        raise HTTPException(404, "关联记录不存在")
    # 清理角色冗余
    char = (await db.execute(select(Character).where(Character.id == cc.character_id))).scalar_one_or_none()
    if char:
        if cc.career_type == "main" and char.main_career_id == cc.career_id:
            char.main_career_id = None
            char.main_career_stage = 0
        elif cc.career_type == "sub":
            subs = [s for s in (char.sub_careers or []) if s.get("career_id") != cc.career_id]
            char.sub_careers = subs
        await db.commit()
    await db.delete(cc)
    await db.commit()
    return {"ok": True}


class CharCareerGenerateReq(BaseModel):
    user_prompt: str = ""


@router.post("/{project_id}/character-careers/auto-assign")
async def auto_assign_careers(
    project_id: int, req: CharCareerGenerateReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """AI 根据角色性格背景 + 职业体系，为未分配职业的角色推荐主职业。"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    # 现有职业
    careers = (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    if not careers:
        raise HTTPException(400, "请先生成职业体系")
    career_list = "\n".join(f"- ID:{c.id} {c.name}（{c.career_type}，{c.category or '通用'}）" for c in careers)
    # 已有主职业的角色
    assigned_ids = [cc.character_id for cc in (await db.execute(
        select(CharacterCareer).where(CharacterCareer.project_id == project_id, CharacterCareer.career_type == "main")
    )).scalars().all()]
    # 待分配角色
    chars = (await db.execute(
        select(Character).where(
            Character.project_id == project_id,
            ~Character.id.in_(assigned_ids) if assigned_ids else True,
        ).limit(20)
    )).scalars().all()
    if not chars:
        return {"count": 0, "message": "所有角色已分配主职业"}
    char_list = "\n".join(f"- ID:{c.id} {c.name}（{c.role or '角色'}，{c.main_career_stage_desc or '无职业'}，性格：{(c.personality or '未知')[:50]}）" for c in chars)

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("career_assign", ai_client, {
        "title": proj.title,
        "genre": proj.genre or "网文",
        "user_prompt": f"""请为以下角色从职业体系中选择最匹配的主职业。

职业体系：
{career_list}

待分配角色：
{char_list}

要求：每个角色分配1个最匹配的主职业(career_type="main")，返回character_id、career_id、current_stage(初始阶段1-3)、started_at。{'额外要求：' + req.user_prompt if req.user_prompt else ''}""",
    })
    if result.get("error"):
        raise HTTPException(500, f"AI 生成失败: {result['error']}")
    data = result.get("json") or []
    if isinstance(data, dict):
        data = data.get("assignments") or data.get("data") or []

    char_id_set = {c.id for c in chars}
    career_id_set = {c.id for c in careers}
    created = []
    for a in data:
        if not isinstance(a, dict):
            continue
        if a.get("character_id") not in char_id_set or a.get("career_id") not in career_id_set:
            continue
        try:
            cc = CharacterCareer(
                project_id=project_id,
                character_id=int(a["character_id"]),
                career_id=int(a["career_id"]),
                career_type="main",
                current_stage=max(1, int(a.get("current_stage", 1))),
                started_at=str(a.get("started_at", ""))[:100],
                source="ai",
            )
            db.add(cc)
            await db.flush()
            # 同步角色冗余
            char = next((c for c in chars if c.id == cc.character_id), None)
            career = next((c for c in careers if c.id == cc.career_id), None)
            if char and career:
                char.main_career_id = cc.career_id
                char.main_career_stage = cc.current_stage
            created.append(cc.to_dict())
        except Exception as e:
            logger.warning(f"[char_career] 解析单条失败: {e}")
    await db.commit()
    return {"count": len(created), "assignments": created}
