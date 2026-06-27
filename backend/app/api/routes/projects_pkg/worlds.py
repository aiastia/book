"""世界观 + 组织 + 职业体系"""

import asyncio
import json
import logging

from app.api.routes.projects_pkg.base import *
from app.core.database import async_session
from app.models.project import Project

router = make_router()
logger = logging.getLogger(__name__)


# ===== 世界设定向量同步 =====


async def _sync_world_memory(
    project_id: int, world_id: int, name: str, category: str, content: str, user_id: int
):
    """创建或更新世界观对应的向量记忆（供章节生成语义检索）。"""
    try:
        from app.models.story_memory import StoryMemory
        from app.services.memory_vector_service import MemoryVectorService, _embed_one

        async with async_session() as s:
            title_prefix = f"[world:{world_id}]"
            # 删除旧记忆（通过 title 前缀匹配）
            old = (
                (
                    await s.execute(
                        select(StoryMemory).where(
                            StoryMemory.project_id == project_id,
                            StoryMemory.title.like(f"{title_prefix}%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for o in old:
                await s.delete(o)
            # 创建新记忆
            memory_text = f"【{category}】{name}\n{content}"
            m = StoryMemory(
                project_id=project_id,
                user_id=user_id,
                memory_type="world",
                title=f"{title_prefix} {name}",
                content=memory_text,
                importance=0.7,
            )
            s.add(m)
            await s.commit()
            await s.refresh(m)
            # 向量化
            try:
                vec = await _embed_one(memory_text[:2000])
                if vec:
                    vs = MemoryVectorService()
                    await vs.add_memory(
                        user_id=user_id or 0,
                        project_id=project_id,
                        memory_id=m.id,
                        content=memory_text,
                        memory_type="world",
                        title=m.title,
                        importance=0.7,
                    )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[world] 向量同步失败 world_id={world_id}: {e}")


async def _delete_world_memory(project_id: int, world_id: int):
    """删除世界观对应的向量记忆。"""
    try:
        from app.models.story_memory import StoryMemory

        async with async_session() as s:
            title_prefix = f"[world:{world_id}]"
            old = (
                (
                    await s.execute(
                        select(StoryMemory).where(
                            StoryMemory.project_id == project_id,
                            StoryMemory.title.like(f"{title_prefix}%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for o in old:
                await s.delete(o)
            await s.commit()
    except Exception as e:
        logger.warning(f"[world] 删除向量记忆失败 world_id={world_id}: {e}")


# ============ 核心世界观（时间/地点/氛围/规则，存于 Project） ============
@router.get("/{project_id}/world-core")
async def get_world_core(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """获取核心世界观（时间/地点/氛围/规则）"""
    p = await get_user_project(db, project_id, user)
    return {
        "world_time_period": p.world_time_period or "",
        "world_location": p.world_location or "",
        "world_atmosphere": p.world_atmosphere or "",
        "world_rules": p.world_rules or "",
    }


@router.put("/{project_id}/world-core")
async def update_world_core(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """手动更新核心世界观"""
    p = await get_user_project(db, project_id, user)
    for k in ["world_time_period", "world_location", "world_atmosphere", "world_rules"]:
        if k in req:
            setattr(p, k, str(req[k]))
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/world-core/generate")
async def generate_world_core(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """AI 生成核心世界观（时间/地点/氛围/规则）并写入 Project"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "world_core_generate",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无",
            "user_prompt": f"请为《{proj.title}》生成核心世界观。",
        },
    )
    check_skill_error(result)
    data = result.get("json") or {}
    if not isinstance(data, dict):
        raise HTTPException(500, "AI 未返回有效世界观")
    proj.world_time_period = str(data.get("world_time_period", ""))[:2000]
    proj.world_location = str(data.get("world_location", ""))[:2000]
    proj.world_atmosphere = str(data.get("world_atmosphere", ""))[:2000]
    proj.world_rules = str(data.get("world_rules", ""))[:2000]
    await db.commit()
    return data


@router.post("/{project_id}/world-core/generate-async")
async def generate_world_core_async(
    project_id: int,
    req: dict = {},
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步生成核心世界观：立即返回 task_id，后台执行（灵感模式兜底可关闭网页）。"""
    proj = await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        await tracker.update(stage="generating", message="AI 正在生成世界观核心设定...")
        async with async_session() as task_db:
            engine, ai_client = await make_engine_and_client(task_db, payload["user_id"])
            result = await engine.execute_skill(
                "world_core_generate",
                ai_client,
                {
                    "title": payload["title"],
                    "genre": payload.get("genre", "网文"),
                    "synopsis": payload.get("synopsis", "暂无"),
                    "user_prompt": f"请为《{payload['title']}》生成核心世界观。",
                },
            )
            if result.get("error"):
                await tracker.fail(result["error"])
                return
            await tracker.update(stage="saving", message="保存世界观...")
            data = result.get("json") or {}
            if isinstance(data, dict):
                proj_obj = (
                    await task_db.execute(
                        select(Project).where(Project.id == payload["project_id"])
                    )
                ).scalar_one_or_none()
                if proj_obj:
                    proj_obj.world_time_period = str(data.get("world_time_period", ""))[:2000]
                    proj_obj.world_location = str(data.get("world_location", ""))[:2000]
                    proj_obj.world_atmosphere = str(data.get("world_atmosphere", ""))[:2000]
                    proj_obj.world_rules = str(data.get("world_rules", ""))[:2000]
                    await task_db.commit()
                    await tracker.complete(message="世界观核心设定已生成")
                else:
                    await tracker.fail("项目不存在")
            else:
                await tracker.fail("AI 未返回有效世界观")

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="world_core",
        title="生成世界观核心设定",
        payload={
            "project_id": project_id,
            "user_id": user.id,
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无",
        },
        runner=_run,
    )
    return {"task_id": task_id}


# ============ 世界观（多条 WorldSetting） ============
@router.get("/{project_id}/worlds")
async def list_worlds(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    result = await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))
    return [
        {"id": w.id, "name": w.name, "category": w.category, "content": w.content}
        for w in result.scalars().all()
    ]


@router.post("/{project_id}/worlds")
async def create_world(
    project_id: int,
    req: WorldSettingCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    ws = WorldSetting(project_id=project_id, **req.model_dump())
    db.add(ws)
    await db.commit()
    await db.refresh(ws)
    return {"id": ws.id}


@router.post("/{project_id}/worlds/generate")
async def generate_world(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """AI 生成详细世界设定条目（地理/历史/种族/势力等），多条存库。"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    world_ctx = ""
    if proj.world_time_period:
        world_ctx += f"时间背景：{proj.world_time_period}\n"
    if proj.world_location:
        world_ctx += f"地理位置：{proj.world_location}\n"
    if proj.world_atmosphere:
        world_ctx += f"氛围基调：{proj.world_atmosphere}\n"
    if proj.world_rules:
        world_ctx += f"世界规则：{proj.world_rules}\n"

    result = await engine.execute_skill(
        "world_detail_generate",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无",
            "world_info": world_ctx or "暂无",
            "user_prompt": req.get("idea", ""),
        },
    )
    check_skill_error(result)
    items = result.get("json") or []
    if not isinstance(items, list):
        items = [items] if isinstance(items, dict) else []
    if not items:
        raise HTTPException(500, "AI 未返回有效设定条目")

    created = []
    for item in items[:10]:
        if isinstance(item, dict) and item.get("name"):
            w = WorldSetting(
                project_id=project_id,
                name=str(item.get("name", ""))[:100],
                category=str(item.get("category", "其他"))[:50],
                content=str(item.get("content", ""))[:2000],
            )
            db.add(w)
            created.append(w)
    await db.commit()
    return {
        "count": len(created),
        "items": [{"name": w.name, "category": w.category} for w in created],
    }


@router.put("/{project_id}/worlds/{world_id}")
async def update_world(
    project_id: int,
    world_id: int,
    req: WorldSettingCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)
    w = (
        await db.execute(
            select(WorldSetting).where(
                WorldSetting.id == world_id, WorldSetting.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "世界设定不存在")
    for key, value in req.model_dump().items():
        setattr(w, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/worlds/{world_id}")
async def delete_world(
    project_id: int,
    world_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)
    w = (
        await db.execute(
            select(WorldSetting).where(
                WorldSetting.id == world_id, WorldSetting.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "世界设定不存在")
    await db.delete(w)
    await db.commit()
    # 删除对应向量记忆
    asyncio.ensure_future(_delete_world_memory(project_id, world_id))
    return {"ok": True}


@router.post("/{project_id}/worlds/reindex-vectors")
async def reindex_world_relation_vectors(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """一键批量回填：将所有世界观设定 + 角色关系同步到向量库。

    后台异步执行，立即返回。
    """
    await get_user_project(db, project_id, user)
    from app.models.character import CharacterRelation

    world_count = await db.scalar(
        select(func.count(WorldSetting.id)).where(WorldSetting.project_id == project_id)
    )
    rel_count = await db.scalar(
        select(func.count(CharacterRelation.id)).where(CharacterRelation.project_id == project_id)
    )
    total = (world_count or 0) + (rel_count or 0)
    if total == 0:
        return {"ok": True, "total": 0, "message": "没有需要同步的数据"}

    async def _run():
        from app.core.database import async_session as _as

        synced = 0
        failed = 0
        async with _as() as task_db:
            # 同步世界观
            worlds = (
                (
                    await task_db.execute(
                        select(WorldSetting).where(WorldSetting.project_id == project_id)
                    )
                )
                .scalars()
                .all()
            )
            for w in worlds:
                try:
                    if not w.content or len(str(w.content).strip()) < 10:
                        logger.warning(f"[reindex] 跳过世界观 id={w.id} '{w.name}'（内容不足10字）")
                        failed += 1
                        continue
                    await _sync_world_memory(
                        project_id, w.id, w.name, w.category, w.content, user.id
                    )
                    synced += 1
                except Exception as e:
                    logger.warning(f"[reindex] 世界观 {w.name} 同步失败: {e}")
                    failed += 1
            # 同步关系
            rels = (
                (
                    await task_db.execute(
                        select(CharacterRelation).where(CharacterRelation.project_id == project_id)
                    )
                )
                .scalars()
                .all()
            )
            for r in rels:
                try:
                    await _sync_relation_memory(project_id, r.id, user.id)
                    synced += 1
                except Exception:
                    pass
        logger.info(
            f"[reindex] 项目 {project_id} 向量回填完成: {synced}/{total}（跳过/失败 {failed}）"
        )

    asyncio.ensure_future(_run())
    return {
        "ok": True,
        "total": total,
        "message": f"正在后台同步 {total} 条数据（{world_count} 个世界观 + {rel_count} 条关系）",
    }


# ============ 组织 ============
@router.get("/{project_id}/organizations")
async def list_orgs(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    await get_user_project(db, project_id, user)  # 权限校验
    result = await db.execute(select(Organization).where(Organization.project_id == project_id))
    return [
        {"id": o.id, "name": o.name, "org_type": o.org_type, "description": o.description}
        for o in result.scalars().all()
    ]


@router.post("/{project_id}/organizations")
async def create_org(
    project_id: int,
    req: OrgCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    org = Organization(project_id=project_id, **req.model_dump())
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {"id": org.id}


@router.put("/{project_id}/organizations/{org_id}")
async def update_org(
    project_id: int,
    org_id: int,
    req: OrgCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    o = (
        await db.execute(
            select(Organization).where(
                Organization.id == org_id, Organization.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "组织不存在")
    for key, value in req.model_dump().items():
        setattr(o, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/organizations/{org_id}")
async def delete_org(
    project_id: int, org_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    o = (
        await db.execute(
            select(Organization).where(
                Organization.id == org_id, Organization.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not o:
        raise HTTPException(404, "组织不存在")
    await db.delete(o)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/organizations/generate")
async def generate_organization(
    project_id: int,
    req: OrgGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """AI 生成单个组织/势力并存库"""
    proj = await get_user_project(db, project_id, user)
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    existing_orgs = (
        "\n".join([f"- {o.name}({o.org_type}): {o.description[:150]}" for o in orgs]) or "暂无"
    )
    characters_info = "\n".join([f"- {c.name}({c.role})" for c in chars]) or "暂无"
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "single_organization_generation",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "existing_organizations": existing_orgs,
            "characters_info": characters_info,
            "world_info": world_info,
            "user_prompt": f"请为这部{proj.genre or '网文'}生成一个组织/势力。{req.user_input}",
        },
    )
    check_skill_error(result)
    org_data = result.get("json") or {}
    if not isinstance(org_data, dict):
        raise HTTPException(500, "AI 返回的组织数据格式不正确")
    # 字段兼容（DB 提示词用 organization_type，代码用 org_type）
    pv = org_data.get("power_value", org_data.get("power_level", 50))
    try:
        pv = int(pv)
    except:
        pv = 50
    org = Organization(
        project_id=project_id,
        name=str(org_data.get("name", ""))[:100],
        org_type=str(
            org_data.get("org_type", org_data.get("organization_type", org_data.get("type", "")))
        )[:50],
        description=str(org_data.get("description", org_data.get("background", "")))[:2000],
        power_value=pv,
        location=str(org_data.get("location", ""))[:200],
        motto=str(org_data.get("motto", org_data.get("organization_purpose", "")))[:200],
        color=str(org_data.get("color", ""))[:20],
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "org_type": org.org_type,
            "description": org.description,
            "power_value": org.power_value,
            "location": org.location,
            "motto": org.motto,
        }
    }


class OrgBatchGenerateRequest(BaseModel):
    count: int = 1
    user_input: str = ""


@router.post("/{project_id}/organizations/generate-async")
async def generate_organization_async(
    project_id: int,
    req: OrgBatchGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步批量生成组织：立即返回 task_id，后台执行。"""
    await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        try:
            async with async_session() as task_db:
                count = payload.get("count", 1)
                user_input = payload.get("user_input", "")
                user_id = payload["user_id"]
                pid = payload["project_id"]

                for i in range(count):
                    await tracker.update(
                        stage="generating",
                        message=f"正在生成第 {i + 1}/{count} 个组织…",
                        progress=int((i / max(count, 1)) * 100),
                    )
                    proj = await task_db.get(Project, pid)
                    orgs = (
                        (
                            await task_db.execute(
                                select(Organization).where(Organization.project_id == pid)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    chars = (
                        (
                            await task_db.execute(
                                select(Character).where(Character.project_id == pid)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    worlds_data = (
                        (
                            await task_db.execute(
                                select(WorldSetting).where(WorldSetting.project_id == pid)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    existing_orgs = (
                        "\n".join(
                            [f"- {o.name}({o.org_type}): {o.description[:150]}" for o in orgs]
                        )
                        or "暂无"
                    )
                    characters_info = "\n".join([f"- {c.name}({c.role})" for c in chars]) or "暂无"
                    world_info = (
                        "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds_data]) or "暂无"
                    )

                    engine, ai_client = await make_engine_and_client(task_db, user_id)
                    result = await engine.execute_skill(
                        "single_organization_generation",
                        ai_client,
                        {
                            "title": proj.title,
                            "genre": proj.genre or "网文",
                            "synopsis": proj.synopsis or "暂无简介",
                            "existing_organizations": existing_orgs,
                            "characters_info": characters_info,
                            "world_info": world_info,
                            "user_prompt": f"请为这部{proj.genre or '网文'}生成一个组织/势力。{user_input}",
                        },
                    )
                    if result.get("error"):
                        await tracker.fail(f"第{i + 1}个失败: {result['error']}")
                        return
                    org_data = result.get("json") or {}
                    if not isinstance(org_data, dict):
                        continue
                    pv = org_data.get("power_value", org_data.get("power_level", 50))
                    try:
                        pv = int(pv)
                    except:
                        pv = 50
                    org = Organization(
                        project_id=pid,
                        name=str(org_data.get("name", ""))[:100],
                        org_type=str(
                            org_data.get(
                                "org_type",
                                org_data.get("organization_type", org_data.get("type", "")),
                            )
                        )[:50],
                        description=str(
                            org_data.get("description", org_data.get("background", ""))
                        )[:2000],
                        power_value=pv,
                        location=str(org_data.get("location", ""))[:200],
                        motto=str(org_data.get("motto", org_data.get("organization_purpose", "")))[
                            :200
                        ],
                        color=str(org_data.get("color", ""))[:20],
                    )
                    task_db.add(org)
                    await task_db.commit()
                await tracker.complete(message=f"生成完成（{count} 个组织）")
        except Exception as e:
            try:
                await tracker.fail(str(e))
            except:
                pass

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="organizations",
        title=f"AI 生成组织（{req.count}个）",
        payload={
            "count": req.count,
            "user_input": req.user_input,
            "project_id": project_id,
            "user_id": user.id,
        },
        runner=_run,
    )
    return {"task_id": task_id}


@router.post("/{project_id}/organizations/auto-analysis")
async def auto_analyze_organizations(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """自动组织分析：预测是否需要新组织"""
    proj = await get_user_project(db, project_id, user)
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    outlines = (
        (
            await db.execute(
                select(Outline)
                .where(Outline.project_id == project_id)
                .order_by(Outline.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    chapters = (
        (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == project_id)
                .order_by(Chapter.chapter_number)
            )
        )
        .scalars()
        .all()
    )
    existing_orgs = (
        json.dumps([{"name": o.name, "org_type": o.org_type} for o in orgs], ensure_ascii=False)
        if orgs
        else "暂无"
    )
    existing_outlines = (
        json.dumps(
            [
                {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary}
                for o in outlines
            ],
            ensure_ascii=False,
        )
        if outlines
        else "暂无"
    )

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "auto_organization_analysis",
        ai_client,
        {
            "chapter_count": str(len(chapters)),
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "existing_outlines": existing_outlines,
            "existing_organizations": existing_orgs,
            "user_prompt": "请分析当前剧情进展，判断是否需要引入新组织/势力。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/organizations/auto-generate")
async def auto_generate_organization(
    project_id: int,
    req: AutoOrgGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """根据分析结果自动生成组织并存库"""
    proj = await get_user_project(db, project_id, user)
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    existing_orgs = "\n".join([f"- {o.name}({o.org_type})" for o in orgs]) or "暂无"
    characters_info = "\n".join([f"- {c.name}({c.role})" for c in chars]) or "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "auto_organization_generation",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "existing_organizations": existing_orgs,
            "existing_characters": characters_info,
            "analysis_result": json.dumps(req.analysis_result, ensure_ascii=False)
            if req.analysis_result
            else "",
            "user_prompt": f"请根据分析结果自动生成一个新组织/势力。{req.specification}",
        },
    )
    check_skill_error(result)
    org_data = result.get("json") or {}
    if not isinstance(org_data, dict):
        raise HTTPException(500, "AI 返回的组织数据格式不正确")
    # 字段兼容（DB 提示词用 organization_type，代码用 org_type）
    pv = org_data.get("power_value", org_data.get("power_level", 50))
    try:
        pv = int(pv)
    except:
        pv = 50
    org = Organization(
        project_id=project_id,
        name=str(org_data.get("name", ""))[:100],
        org_type=str(
            org_data.get("org_type", org_data.get("organization_type", org_data.get("type", "")))
        )[:50],
        description=str(org_data.get("description", org_data.get("background", "")))[:2000],
        power_value=pv,
        location=str(org_data.get("location", ""))[:200],
        motto=str(org_data.get("motto", org_data.get("organization_purpose", "")))[:200],
        color=str(org_data.get("color", ""))[:20],
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "org_type": org.org_type,
            "description": org.description,
            "power_value": org.power_value,
            "location": org.location,
            "motto": org.motto,
        }
    }


# ============ 职业体系 ============
from app.models.career import Career


@router.get("/{project_id}/careers")
async def list_careers(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """列出项目的所有职业"""
    result = await db.execute(select(Career).where(Career.project_id == project_id))
    return [c.to_dict() for c in result.scalars().all()]


@router.post("/{project_id}/careers")
async def create_career(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """手动创建职业"""
    await get_user_project(db, project_id, user)
    career = Career(
        project_id=project_id,
        name=req.get("name", ""),
        career_type=req.get("career_type", "main"),
        category=req.get("category", ""),
        description=req.get("description", ""),
        stages=req.get("stages", []),
        abilities=req.get("abilities", []),
        attributes=req.get("attributes", {}),
    )
    db.add(career)
    await db.commit()
    await db.refresh(career)
    return career.to_dict()


@router.put("/{project_id}/careers/{career_id}")
async def update_career(
    project_id: int,
    career_id: int,
    req: dict,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)  # 权限校验
    c = (
        await db.execute(
            select(Career).where(Career.id == career_id, Career.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "职业不存在")
    for k in [
        "name",
        "career_type",
        "category",
        "description",
        "stages",
        "abilities",
        "attributes",
    ]:
        if k in req:
            setattr(c, k, req[k])
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/careers/{career_id}")
async def delete_career(
    project_id: int,
    career_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    c = (
        await db.execute(
            select(Career).where(Career.id == career_id, Career.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "职业不存在")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/career-system/generate")
async def generate_career_system(
    project_id: int,
    req: dict = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """AI 生成职业体系并存库。

    支持追加生成：传入 req = { append: true, count: N, career_type: "main"/"sub", user_prompt: "..." }
    append=true 时不会删除已有职业，只追加新的（且提示 AI 避开已存在的）。
    """
    req = req or {}
    append_mode = req.get("append", False)
    count = req.get("count", 0)
    req_type = req.get("career_type", "")
    user_prompt = req.get("user_prompt", "")

    proj = await get_user_project(db, project_id, user)
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"

    # 已有职业（追加模式下告知 AI 避开）
    existing_info = ""
    if append_mode:
        existing = (
            (await db.execute(select(Career).where(Career.project_id == project_id)))
            .scalars()
            .all()
        )
        if existing:
            existing_info = "\n已有职业（不要重复生成这些）：\n" + "\n".join(
                f"- {c.name}（{c.career_type}，{c.category}）" for c in existing
            )

    engine, ai_client = await make_engine_and_client(db, user.id)
    default_prompt = f"请为这部{proj.genre or '网文'}生成职业体系。如果该题材不需要职业体系（如快穿甜宠/纯言情等），返回空数组即可。"
    if count and count > 0:
        type_hint = f"生成 {count} 个{'主职业' if req_type == 'main' else '副职业' if req_type == 'sub' else '职业'}"
        if append_mode:
            default_prompt = (
                f"在现有职业体系基础上{type_hint}，补充新的职业（不要与已有重复）。{existing_info}"
            )
        else:
            default_prompt += f" 本次需{type_hint}。"
    elif append_mode:
        default_prompt = f"在现有职业体系基础上补充新的职业（不要与已有重复）。{existing_info}"
    if user_prompt:
        default_prompt += f"\n额外要求：{user_prompt}"

    result = await engine.execute_skill(
        "career_system_generation",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "world_info": world_info + existing_info,
            "user_prompt": default_prompt,
        },
    )
    check_skill_error(result)
    data = result.get("json") or {}
    # AI 可能返回 {careers:[...]} / {main_careers:[...], sub_careers:[...]} / {main_career:{...}} / 裸数组
    careers_list = []
    if isinstance(data, list):
        careers_list = data
    elif isinstance(data, dict):
        if "careers" in data and isinstance(data["careers"], list):
            careers_list = data["careers"]
        elif data.get("name"):
            careers_list = [data]
        else:
            # main_careers（复数数组，提示词要求的格式）+ sub_careers
            for mc in data.get("main_careers") or []:
                if isinstance(mc, dict):
                    mc.setdefault("career_type", "main")
                    careers_list.append(mc)
            # 兼容单数 main_career
            if data.get("main_career") and isinstance(data["main_career"], dict):
                mc = data["main_career"]
                mc.setdefault("career_type", "main")
                careers_list.append(mc)
            for sc in data.get("sub_careers") or []:
                if isinstance(sc, dict):
                    sc.setdefault("career_type", "sub")
                    careers_list.append(sc)

    # 追加模式下，过滤掉与已有同名的（避免重复）
    existing_names = set()
    if append_mode:
        existing = (
            (await db.execute(select(Career).where(Career.project_id == project_id)))
            .scalars()
            .all()
        )
        existing_names = {c.name for c in existing}

    created = []
    for item in careers_list:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item.get("name", ""))
        if name in existing_names:
            continue  # 跳过重复
        # 追加模式 + 指定类型时，强制覆盖类型
        c_type = str(item.get("career_type", "main"))
        if append_mode and req_type in ("main", "sub"):
            c_type = req_type
        c = Career(
            project_id=project_id,
            name=name,
            career_type=c_type,
            category=str(item.get("category", "")),
            description=str(item.get("description", "")),
            stages=item.get("stages", item.get("advancement_stages", [])),
            abilities=item.get("abilities", item.get("special_abilities", [])),
            attributes=item.get("attributes", {}),
        )
        db.add(c)
        created.append(c.to_dict())
    await db.commit()
    return {"careers": created, "count": len(created)}
