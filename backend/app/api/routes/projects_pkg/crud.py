"""项目 CRUD：创建/列表/详情/更新/删除/导入导出"""
from datetime import datetime
from app.api.routes.projects_pkg.base import *


router = make_router()


@router.post("")
async def create_project(req: ProjectCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    project = Project(user_id=user.id, **req.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"id": project.id, "title": project.title}


@router.get("")
async def list_projects(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
    )
    projects = result.scalars().all()
    # 批量取每个项目的当前总字数（单次 group-by 查询，避免 N+1）
    word_sums = {}
    if projects:
        rows = await db.execute(
            select(Chapter.project_id, func.coalesce(func.sum(Chapter.word_count), 0))
            .where(Chapter.project_id.in_([p.id for p in projects]))
            .group_by(Chapter.project_id)
        )
        word_sums = {r[0]: r[1] for r in rows.all()}
    return [
        {
            "id": p.id,
            "title": p.title,
            "genre": p.genre,
            "synopsis": (p.synopsis or "")[:100],
            "status": p.status,
            "target_word_count": p.target_word_count,
            "current_word_count": word_sums.get(p.id, 0),
            "chapter_count": p.chapter_count,
            "cover_url": p.cover_url,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    p = await get_user_project(db, project_id, user)
    # 动态计算当前总字数（从 chapters 表 sum，不依赖可能从未更新的 current_word_count 列）
    word_sum = await db.scalar(
        select(func.coalesce(func.sum(Chapter.word_count), 0))
        .where(Chapter.project_id == project_id)
    )
    return {
        "id": p.id,
        "title": p.title,
        "genre": p.genre,
        "synopsis": p.synopsis or "",
        "status": p.status,
        "target_word_count": p.target_word_count,
        "current_word_count": word_sum,
        "chapter_count": p.chapter_count,
        "narrative_pov": p.narrative_pov,
        "outline_mode": p.outline_mode or "one_to_one",
        "cover_url": p.cover_url,
        "writing_style": p.writing_style,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.put("/{project_id}")
async def update_project(project_id: int, req: ProjectUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    p = await get_user_project(db, project_id, user)
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """删除项目（级联删除所有关联数据）"""
    await get_user_project(db, project_id, user)
    # 级联删除关联数据（SQLite 不一定有 ON DELETE CASCADE，手动删更稳）
    from app.models.outline import Outline
    from app.models.character import Character, CharacterRelation
    from app.models.world import WorldSetting
    from app.models.organization import Organization
    from app.models.foreshadow import Foreshadow
    from app.models.plot_analysis import PlotAnalysis
    from app.models.story_memory import StoryMemory
    from app.models.career import Career
    from app.models.writing_style import WritingStyle
    import json

    for Model in [Chapter, Outline, Character, CharacterRelation, WorldSetting,
                  Organization, Foreshadow, PlotAnalysis, StoryMemory, Career]:
        items = (await db.execute(select(Model).where(Model.project_id == project_id))).scalars().all()
        for it in items:
            await db.delete(it)
    p = (await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))).scalar_one_or_none()
    if p:
        await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/export")
async def export_project(
    project_id: int,
    format: str = "json",  # json / txt
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """导出项目完整数据。

    format=json：全量 JSON（含记忆/分析/物品/地点等所有表，#22）
    format=txt：整书纯文本导出
    """
    p = await get_user_project(db, project_id, user)
    from app.models.outline import Outline
    from app.models.character import Character, CharacterRelation
    from app.models.world import WorldSetting
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.foreshadow import Foreshadow
    from app.models.career import Career
    from app.models.item import Item
    from app.models.location import Location
    from app.models.story_memory import StoryMemory
    from app.models.plot_analysis import PlotAnalysis
    from fastapi.responses import PlainTextResponse

    def to_dict(obj):
        if not obj:
            return None
        return {c.name: getattr(obj, c.name) for c in obj.__table__.columns
                if c.name not in ('created_at', 'updated_at')}

    def list_dicts(items):
        return [{c.name: getattr(it, c.name) for c in it.__table__.columns
                 if c.name not in ('id', 'project_id', 'created_at', 'updated_at')} for it in items]

    # TXT 整书导出
    if format == "txt":
        from urllib.parse import quote
        chapters = (await db.execute(
            select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number)
        )).scalars().all()
        lines = [p.title or "未命名", ""]
        if p.synopsis:
            lines += [p.synopsis, ""]
        lines.append("=" * 40)
        for ch in chapters:
            lines += ["", f"第{ch.chapter_number}章 {ch.title or ''}", ""]
            lines.append(ch.content or "")
            lines.append("")
        safe_name = quote(p.title or "book", safe="")
        return PlainTextResponse(
            "\n".join(lines), media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}.txt"},
        )

    # 全量 JSON 导出
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    rels = (await db.execute(select(CharacterRelation).where(CharacterRelation.project_id == project_id))).scalars().all()
    orgs = (await db.execute(select(Organization).where(Organization.project_id == project_id))).scalars().all()
    members = (await db.execute(select(OrganizationMember).where(OrganizationMember.project_id == project_id))).scalars().all()
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    chapters = (await db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number))).scalars().all()
    foreshadows = (await db.execute(select(Foreshadow).where(Foreshadow.project_id == project_id))).scalars().all()
    careers = (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    items = (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    locations = (await db.execute(select(Location).where(Location.project_id == project_id))).scalars().all()
    memories = (await db.execute(select(StoryMemory).where(StoryMemory.project_id == project_id))).scalars().all()
    analyses = (await db.execute(select(PlotAnalysis).where(PlotAnalysis.project_id == project_id))).scalars().all()

    return {
        "project": to_dict(p),
        "worlds": list_dicts(worlds),
        "characters": list_dicts(chars),
        "character_relations": list_dicts(rels),
        "organizations": list_dicts(orgs),
        "organization_members": list_dicts(members),
        "outlines": list_dicts(outlines),
        "chapters": list_dicts(chapters),
        "foreshadows": list_dicts(foreshadows),
        "careers": list_dicts(careers),
        "items": list_dicts(items),
        "locations": list_dicts(locations),
        "memories": list_dicts(memories),
        "analyses": list_dicts(analyses),
        "_version": 2,
        "_exported_at": datetime.utcnow().isoformat(),
    }


@router.post("/import")
async def import_project(req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """导入项目数据（从 export 的 JSON 恢复，创建为新项目，含全量表 #22）。"""
    from app.models.outline import Outline
    from app.models.character import Character, CharacterRelation
    from app.models.world import WorldSetting
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.foreshadow import Foreshadow
    from app.models.career import Career
    from app.models.item import Item
    from app.models.location import Location
    from app.models.story_memory import StoryMemory
    from app.models.plot_analysis import PlotAnalysis
    from datetime import datetime

    proj_data = req.get("project", {})
    # 创建新项目（不沿用原 id）
    new_proj = Project(
        user_id=user.id,
        title=str(proj_data.get("title", "导入项目")) + "（导入）",
        genre=proj_data.get("genre", ""),
        synopsis=proj_data.get("synopsis", ""),
        target_word_count=proj_data.get("target_word_count", 0),
        narrative_pov=proj_data.get("narrative_pov", "第三人称"),
        world_time_period=proj_data.get("world_time_period", ""),
        world_location=proj_data.get("world_location", ""),
        world_atmosphere=proj_data.get("world_atmosphere", ""),
        world_rules=proj_data.get("world_rules", ""),
        cover_url=proj_data.get("cover_url", ""),
    )
    db.add(new_proj)
    await db.commit()
    await db.refresh(new_proj)

    # ID 重映射（旧角色 ID → 新角色 ID，用于关系表）
    char_id_map = {}

    def add_all(Model, items, id_mapper=None):
        for it in items:
            if isinstance(it, dict):
                data = {k: v for k, v in it.items() if k != "id"}
                obj = Model(project_id=new_proj.id, **data)
                db.add(obj)
                if id_mapper and it.get("id") is not None:
                    pass  # ID 映射在 flush 后处理

        if id_mapper:
            db.flush()

    # 先导入角色（关系表依赖角色 id）
    char_items = req.get("characters", [])
    old_char_ids = []
    new_chars = []
    for it in char_items:
        if isinstance(it, dict):
            data = {k: v for k, v in it.items() if k != "id"}
            obj = Character(project_id=new_proj.id, **data)
            db.add(obj)
            new_chars.append((it.get("id"), obj))
            old_char_ids.append(it.get("id"))
    await db.flush()
    for old_id, obj in new_chars:
        char_id_map[old_id] = obj.id

    # 关系表（重映射角色 id）
    for it in req.get("character_relations", []):
        if isinstance(it, dict):
            data = {k: v for k, v in it.items() if k != "id"}
            if "from_character_id" in data and data["from_character_id"] in char_id_map:
                data["from_character_id"] = char_id_map[data["from_character_id"]]
            if "to_character_id" in data and data["to_character_id"] in char_id_map:
                data["to_character_id"] = char_id_map[data["to_character_id"]]
            db.add(CharacterRelation(project_id=new_proj.id, **data))

    # 其余表（无 id 依赖）
    add_all(WorldSetting, req.get("worlds", []))
    add_all(Organization, req.get("organizations", []))
    add_all(Outline, req.get("outlines", []))
    add_all(Chapter, req.get("chapters", []))
    add_all(Foreshadow, req.get("foreshadows", []))
    add_all(Career, req.get("careers", []))
    add_all(Item, req.get("items", []))
    add_all(Location, req.get("locations", []))
    add_all(OrganizationMember, req.get("organization_members", []))
    add_all(StoryMemory, req.get("memories", []))
    add_all(PlotAnalysis, req.get("analyses", []))
    await db.commit()
    return {"id": new_proj.id, "title": new_proj.title}
