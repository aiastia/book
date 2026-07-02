"""项目 CRUD：创建/列表/详情/更新/删除/导入导出"""

import json
from datetime import datetime

from app.api.routes.projects_pkg.base import *
from app.services.json_helper import loads_json

router = make_router()


@router.post("")
async def create_project(
    req: ProjectCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
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
    # 批量取每个项目的当前总字数 + 实际章节数（单次 group-by 查询，避免 N+1）
    word_sums = {}
    chapter_counts = {}
    if projects:
        rows = await db.execute(
            select(
                Chapter.project_id,
                func.coalesce(func.sum(Chapter.word_count), 0),
                func.count(Chapter.id),
            )
            .where(Chapter.project_id.in_([p.id for p in projects]))
            .group_by(Chapter.project_id)
        )
        for r in rows.all():
            word_sums[r[0]] = r[1]
            chapter_counts[r[0]] = r[2]
    return [
        {
            "id": p.id,
            "title": p.title,
            "genre": p.genre,
            "synopsis": (p.synopsis or "")[:100],
            "status": p.status,
            "target_word_count": p.target_word_count,
            "current_word_count": word_sums.get(p.id, 0),
            "chapter_count": chapter_counts.get(p.id, 0),
            "outline_mode": p.outline_mode or "one_to_one",
            "narrative_pov": p.narrative_pov or "第三人称",
            "cover_url": p.cover_url,
            "cover_prompt": p.cover_prompt or "",
            "pen_name": p.pen_name or "",
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }
        for p in projects
    ]


@router.get("/{project_id}")
async def get_project(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    p = await get_user_project(db, project_id, user)
    # 动态计算当前总字数 + 实际章节数（从 chapters 表查，不依赖项目表的静态字段）
    word_sum = await db.scalar(
        select(func.coalesce(func.sum(Chapter.word_count), 0)).where(
            Chapter.project_id == project_id
        )
    )
    actual_chapter_count = await db.scalar(
        select(func.count(Chapter.id)).where(Chapter.project_id == project_id)
    )
    return {
        "id": p.id,
        "title": p.title,
        "genre": p.genre,
        "synopsis": p.synopsis or "",
        "status": p.status,
        "target_word_count": p.target_word_count,
        "current_word_count": word_sum,
        "chapter_count": actual_chapter_count or 0,
        "narrative_pov": p.narrative_pov,
        "outline_mode": p.outline_mode or "one_to_one",
        "cover_url": p.cover_url,
        "cover_prompt": p.cover_prompt or "",
        "pen_name": p.pen_name or "",
        "writing_style": p.writing_style,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.put("/{project_id}")
async def update_project(
    project_id: int,
    req: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    p = await get_user_project(db, project_id, user)
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(p, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}")
async def delete_project(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """删除项目（级联删除所有关联数据）"""
    await get_user_project(db, project_id, user)
    # 级联删除关联数据（SQLite 不一定有 ON DELETE CASCADE，手动删更稳）

    from app.models.career import Career
    from app.models.character import Character, CharacterRelation
    from app.models.character_career import CharacterCareer
    from app.models.foreshadow import Foreshadow
    from app.models.organization import Organization
    from app.models.outline import Outline
    from app.models.plot_analysis import PlotAnalysis
    from app.models.story_memory import StoryMemory
    from app.models.world import WorldSetting

    for Model in [
        Chapter,
        Outline,
        Character,
        CharacterRelation,
        WorldSetting,
        Organization,
        Foreshadow,
        PlotAnalysis,
        StoryMemory,
        Career,
    ]:
        items = (
            (await db.execute(select(Model).where(Model.project_id == project_id))).scalars().all()
        )
        for it in items:
            await db.delete(it)
    p = (
        await db.execute(
            select(Project).where(Project.id == project_id, Project.user_id == user.id)
        )
    ).scalar_one_or_none()
    if p:
        await db.delete(p)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/export")
async def export_project(
    project_id: int,
    format: str = "json",  # json / txt
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """导出项目完整数据。

    format=json：全量 JSON（含记忆/分析/物品/地点等所有表，#22）
    format=txt：整书纯文本导出
    """
    p = await get_user_project(db, project_id, user)
    from fastapi.responses import PlainTextResponse

    from app.models.career import Career
    from app.models.character import Character, CharacterRelation
    from app.models.character_career import CharacterCareer
    from app.models.foreshadow import Foreshadow
    from app.models.item import Item
    from app.models.location import Location
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.outline import Outline
    from app.models.plot_analysis import PlotAnalysis
    from app.models.story_memory import StoryMemory
    from app.models.world import WorldSetting

    def to_dict(obj):
        if not obj:
            return None
        return {
            c.name: getattr(obj, c.name)
            for c in obj.__table__.columns
            if c.name not in ("created_at", "updated_at")
        }

    def list_dicts(items):
        return [
            {
                c.name: getattr(it, c.name)
                for c in it.__table__.columns
                if c.name not in ("id", "project_id", "created_at", "updated_at")
            }
            for it in items
        ]

    # TXT 整书导出
    if format == "txt":
        from urllib.parse import quote

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
        lines = [p.title or "未命名", ""]
        lines.append("=" * 40)
        for ch in chapters:
            lines += ["", f"第{ch.chapter_number}章 {ch.title or ''}", ""]
            lines.append(ch.content or "")
            lines.append("")
        safe_name = quote(p.title or "book", safe="")
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}.txt"},
        )

    # 全量 JSON 导出
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
        .scalars()
        .all()
    )
    rels = (
        (
            await db.execute(
                select(CharacterRelation).where(CharacterRelation.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    members = (
        (
            await db.execute(
                select(OrganizationMember).where(OrganizationMember.project_id == project_id)
            )
        )
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
    foreshadows = (
        (await db.execute(select(Foreshadow).where(Foreshadow.project_id == project_id)))
        .scalars()
        .all()
    )
    careers = (
        (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    )
    char_careers = (
        (await db.execute(select(CharacterCareer).where(CharacterCareer.project_id == project_id)))
        .scalars()
        .all()
    )
    items = (await db.execute(select(Item).where(Item.project_id == project_id))).scalars().all()
    locations = (
        (await db.execute(select(Location).where(Location.project_id == project_id)))
        .scalars()
        .all()
    )
    memories = (
        (await db.execute(select(StoryMemory).where(StoryMemory.project_id == project_id)))
        .scalars()
        .all()
    )
    analyses = (
        (await db.execute(select(PlotAnalysis).where(PlotAnalysis.project_id == project_id)))
        .scalars()
        .all()
    )

    return {
        "project": to_dict(p),
        "worlds": list_dicts(worlds),
        "characters": [
            {
                c.name: getattr(it, c.name)
                for c in it.__table__.columns
                if c.name not in ("project_id", "created_at", "updated_at")
            }
            for it in chars
        ],
        "character_relations": list_dicts(rels),
        "organizations": list_dicts(orgs),
        "organization_members": list_dicts(members),
        "outlines": list_dicts(outlines),
        "chapters": list_dicts(chapters),
        "foreshadows": list_dicts(foreshadows),
        "careers": list_dicts(careers),
        "character_careers": list_dicts(char_careers),
        "items": list_dicts(items),
        "locations": list_dicts(locations),
        "memories": list_dicts(memories),
        "analyses": list_dicts(analyses),
        "_version": 2,
        "_exported_at": datetime.utcnow().isoformat(),
    }


def _convert_mumu_to_native(mumu: dict) -> dict:
    """将 MuMuAINovel 导出格式转换为本系统原生导入格式。

    mumu 格式特征：
      - version: "1.x.x"
      - project: {title, genre, synopsis, narrative_pov, ...}
      - chapters: [{title, content, chapter_number, status, word_count, summary, expansion_plan}]
      - characters: [{name, role, personality, background, appearance, age, gender, ...}]
      - outlines: [{title, content, structure, order_index}]
      - relationships: [{source_name, target_name, relationship_name, intimacy_level}]
      - organizations: [{character_name, parent_org_name, power_level, ...}]
      - organization_members: [{organization_name, character_name, position, rank}]
      - careers: [{name, type, stages, ...}]
      - character_careers: [{character_name, career_name, current_stage}]
      - story_memories: [{chapter_title, memory_type, title, content, ...}]
      - plot_analysis: [{chapter_title, plot_stage, conflict_level, ...}]
      - writing_styles: [{name, style_type, prompt_content}]
    """
    # project
    proj = mumu.get("project", {}) or {}

    # characters → 同时分离 organization（is_organization=True 的）
    char_list = []
    org_map = {}  # name → org dict，自动去重（organizations 数组优先）
    for c in mumu.get("characters", []):
        item = {
            "name": c.get("name", ""),
            "age": c.get("age", ""),
            "gender": c.get("gender", ""),
            "role": c.get("role_type") or c.get("role", ""),
            "personality": c.get("personality", ""),
            "background": c.get("background", ""),
            "appearance": c.get("appearance", ""),
            "avatar_url": c.get("avatar_url", ""),
        }
        if c.get("is_organization"):
            org_map[c.get("name", "")] = {
                "name": c.get("name", ""),
                "power_level": c.get("power_level", 50),
                "location": c.get("location", ""),
                "motto": c.get("motto", ""),
                "color": c.get("color", ""),
            }
        else:
            char_list.append(item)

    # organizations + members（organizations 数组覆盖同名的 is_organization 角色）
    for o in mumu.get("organizations", []):
        org_map[o.get("character_name", "")] = {
            "name": o.get("character_name", ""),
            "power_level": o.get("power_level", 50),
            "location": o.get("location", ""),
            "motto": o.get("motto", ""),
            "color": o.get("color", ""),
        }
    org_list = list(org_map.values())

    # relationships → character_relations（用 name 不用 id，导入时建完角色再映射）
    rel_list = []
    for r in mumu.get("relationships", []):
        rel_list.append({
            "from_character_name": r.get("source_name", ""),
            "to_character_name": r.get("target_name", ""),
            "relation_type": r.get("relationship_name", ""),
            "intimacy": r.get("intimacy_level", 50),
            "status": r.get("status", "active"),
            "description": r.get("description", ""),
        })

    org_member_list = []
    for m in mumu.get("organization_members", []):
        org_member_list.append({
            "organization_name": m.get("organization_name", ""),
            "character_name": m.get("character_name", ""),
            "position": m.get("position", ""),
            "rank": m.get("rank", 0),
            "status": m.get("status", "active"),
            "loyalty": m.get("loyalty", 50),
            "contribution": m.get("contribution", 0),
        })

    # outlines
    outline_list = []
    for o in mumu.get("outlines", []):
        struct = o.get("structure")
        if isinstance(struct, str):
            try:
                struct = loads_json(struct)
            except Exception:
                struct = None
        outline_list.append({
            "title": o.get("title", ""),
            "summary": o.get("content", ""),
            "structure": struct,
            "chapter_number": o.get("order_index") or 1,
        })

    # chapters
    chapter_list = []
    for c in mumu.get("chapters", []):
        chapter_list.append({
            "title": c.get("title", ""),
            "content": c.get("content", ""),
            "chapter_number": c.get("chapter_number", 1),
            "status": c.get("status", "draft"),
            "word_count": c.get("word_count", 0),
            "summary": c.get("summary", ""),
            "expansion_plan": c.get("expansion_plan"),
            "outline_title": c.get("outline_title"),  # 1-N: 用于重建大纲关联
            "sub_index": c.get("sub_index"),
        })

    # careers
    career_list = []
    for c in mumu.get("careers", []):
        stages_raw = c.get("stages", "[]")
        # MumuAINovel 的 stages 可能是 JSON 字符串，需解析为 list
        if isinstance(stages_raw, str):
            try:
                stages_raw = loads_json(stages_raw)
            except Exception:
                stages_raw = []
        career_list.append({
            "name": c.get("name", ""),
            "career_type": c.get("type", "main"),
            "description": c.get("description", ""),
            "category": c.get("category", ""),
            "stages": stages_raw,
            "source": c.get("source", "ai"),
        })

    # story_memories
    memory_list = []
    for m in mumu.get("story_memories", []):
        memory_list.append({
            "memory_type": m.get("memory_type", "plot"),
            "title": m.get("title", ""),
            "content": m.get("content", ""),
            "full_context": m.get("full_context", ""),
            "related_characters": m.get("related_characters", []),
            "related_locations": m.get("related_locations", []),
            "tags": m.get("tags", []),
            "importance_score": m.get("importance_score", 0.5),
            "story_timeline": m.get("story_timeline", 0),
            "is_foreshadow": m.get("is_foreshadow", 0),
        })

    # plot_analysis
    analysis_list = []
    for p in mumu.get("plot_analysis", []):
        analysis_list.append({
            "plot_stage": p.get("plot_stage"),
            "conflict_level": p.get("conflict_level"),
            "conflict_types": p.get("conflict_types", []),
            "emotional_tone": p.get("emotional_tone"),
            "emotional_intensity": p.get("emotional_intensity"),
            "emotional_curve": p.get("emotional_curve"),
            "hooks": p.get("hooks", []),
            "hooks_count": p.get("hooks_count", 0),
            "foreshadows": p.get("foreshadows", []),
            "plot_points": p.get("plot_points", []),
            "pacing": p.get("pacing"),
            "overall_quality_score": p.get("overall_quality_score"),
            "analysis_report": p.get("analysis_report"),
            "suggestions": p.get("suggestions", []),
        })

    # character_careers（mumu 格式用 name，导入时映射为 id）
    char_career_list = []
    for cc in mumu.get("character_careers", []):
        char_career_list.append({
            "character_name": cc.get("character_name", ""),
            "career_name": cc.get("career_name", ""),
            "career_type": cc.get("career_type", "main"),
            "current_stage": cc.get("current_stage", 1),
            "stage_progress": cc.get("stage_progress", 0),
            "source": cc.get("source", "ai"),
        })

    # foreshadows（mumu 没有独立的 foreshadow 表，从 story_memories 里 is_foreshadow=1 提取）
    foreshadow_list = []
    for m in mumu.get("story_memories", []):
        if m.get("is_foreshadow"):
            foreshadow_list.append({
                "title": m.get("title", ""),
                "content": m.get("content", ""),
                "status": "active",
                "type": "foreshadow",
                "strength": m.get("foreshadow_strength", 0.5),
            })

    return {
        "project": {
            "title": proj.get("title", "导入项目"),
            "genre": proj.get("genre", ""),
            "synopsis": proj.get("synopsis") or proj.get("description", ""),
            "narrative_pov": proj.get("narrative_pov", "第三人称"),
            "world_time_period": proj.get("world_time_period", ""),
            "world_location": proj.get("world_location", ""),
            "world_atmosphere": proj.get("world_atmosphere", ""),
            "world_rules": proj.get("world_rules", ""),
            "cover_url": proj.get("cover_url", ""),
            "outline_mode": proj.get("outline_mode", "one_to_one"),
            "theme": proj.get("theme", ""),
        },
        "characters": char_list,
        "character_relations": rel_list,
        "organizations": org_list,
        "organization_members": org_member_list,
        "outlines": outline_list,
        "chapters": chapter_list,
        "foreshadows": foreshadow_list,
        "careers": career_list,
        "character_careers": char_career_list,
        "items": [],
        "locations": [],
        "memories": memory_list,
        "analyses": analysis_list,
        "worlds": [],
        "_version": 2,
        "_converted_from": "mumu",
    }


@router.post("/import")
async def import_project(
    req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """导入项目数据（从 export 的 JSON 恢复，创建为新项目，含全量表 #22）。

    自动识别两种格式：
    - 原生格式（_version=2, project/characters/outlines/... 顶层键）
    - mumu 格式（version=1.x, project/chapters/characters/relationships/...）
    """

    # ===== 格式识别 + 转换 =====
    is_mumu = (
        "version" in req and isinstance(req.get("version"), str)
        and req.get("version", "").startswith("1.")
        and "chapters" in req
        and "_version" not in req
    )
    if is_mumu:
        req = _convert_mumu_to_native(req)

    from app.models.career import Career
    from app.models.character import Character, CharacterRelation
    from app.models.character_career import CharacterCareer
    from app.models.foreshadow import Foreshadow
    from app.models.item import Item
    from app.models.location import Location
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember
    from app.models.outline import Outline
    from app.models.plot_analysis import PlotAnalysis
    from app.models.story_memory import StoryMemory
    from app.models.world import WorldSetting

    proj_data = req.get("project", {})
    # Mumu 格式 description/theme → 系统 synopsis/settings
    if not proj_data.get("synopsis") and proj_data.get("description"):
        proj_data = dict(proj_data)
        proj_data["synopsis"] = proj_data.pop("description")
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
        outline_mode=proj_data.get("outline_mode", "one_to_one"),
    )
    db.add(new_proj)
    await db.commit()
    await db.refresh(new_proj)
    # 补充 theme 到 settings
    if proj_data.get("theme"):
        settings = dict(new_proj.settings or {})
        settings["theme"] = proj_data["theme"]
        new_proj.settings = settings
        await db.commit()

    # ID 重映射（旧角色 ID → 新角色 ID，用于关系表）
    char_id_map = {}

    def add_all(Model, items):
        valid_cols = {c.name for c in Model.__table__.columns}
        for it in items:
            if isinstance(it, dict):
                data = {k: v for k, v in it.items() if k != "id" and k in valid_cols}
                obj = Model(project_id=new_proj.id, **data)
                db.add(obj)

    # 先导入角色（关系表依赖角色 id）
    char_items = req.get("characters", [])
    old_char_ids = []
    new_chars = []
    char_name_map = {}  # name → new id（用于 mumu 格式的关系映射）
    char_valid_cols = {c.name for c in Character.__table__.columns}
    _role_map = {"protagonist": "主角", "supporting": "配角", "villain": "反派", "passerby": "路人"}
    for it in char_items:
        if isinstance(it, dict):
            data = {k: v for k, v in it.items() if k != "id" and k in char_valid_cols}
            # mumu 格式 traits → tags
            if "tags" not in data and "traits" in it:
                data["tags"] = it["traits"]
            # role 值翻译（转换器可能已映射 role_type→role，但值仍是英文）
            if data.get("role") in _role_map:
                data["role"] = _role_map[data["role"]]
            obj = Character(project_id=new_proj.id, **data)
            db.add(obj)
            new_chars.append((it.get("id"), obj))
            old_char_ids.append(it.get("id"))
            if obj.name:
                char_name_map[obj.name] = obj
    await db.flush()
    for old_id, obj in new_chars:
        char_id_map[old_id] = obj.id

    # 关系表（支持 id 重映射 或 name 查找）
    for it in req.get("character_relations", []):
        if isinstance(it, dict):
            data = {k: v for k, v in it.items() if k != "id"}
            # id 重映射（原生格式）
            if "from_character_id" in data and data["from_character_id"] in char_id_map:
                data["from_character_id"] = char_id_map[data["from_character_id"]]
            if "to_character_id" in data and data["to_character_id"] in char_id_map:
                data["to_character_id"] = char_id_map[data["to_character_id"]]
            # name 查找（mumu 格式）
            if "from_character_name" in data:
                obj = char_name_map.get(data.pop("from_character_name"))
                if obj:
                    data["from_character_id"] = obj.id
            if "to_character_name" in data:
                obj = char_name_map.get(data.pop("to_character_name"))
                if obj:
                    data["to_character_id"] = obj.id
            if data.get("from_character_id") and data.get("to_character_id"):
                db.add(CharacterRelation(project_id=new_proj.id, **data))

    # 其余表（无 id 依赖）
    add_all(WorldSetting, req.get("worlds", []))
    add_all(Organization, req.get("organizations", []))
    add_all(Outline, req.get("outlines", []))
    await db.flush()

    # 重建 1-N 章节关联：优先用 outline_title 匹配，回退到 outline_id 原序号
    outline_title_map = {}
    outline_oldid_map = {}  # 旧 outline_id → 新 outline_id
    outlines_db = (
        (await db.execute(select(Outline).where(Outline.project_id == new_proj.id)))
        .scalars().all()
    )
    for idx, o in enumerate(outlines_db):
        if o.title:
            outline_title_map[o.title] = o.id
        # 按顺序对应（导出时已去掉 id，按顺序导入，idx 对应原序号）
        outline_oldid_map[idx + 1] = o.id

    for it in req.get("chapters", []):
        if isinstance(it, dict):
            data = {k: v for k, v in it.items() if k != "id"}
            ot = data.pop("outline_title", None)
            old_oid = data.pop("outline_id", None)
            new_oid = None
            # 优先用 title 匹配（mumu 格式）
            if ot and ot in outline_title_map:
                new_oid = outline_title_map[ot]
            # 回退用 old_id 顺序匹配（原生格式）
            elif old_oid and old_oid in outline_oldid_map:
                new_oid = outline_oldid_map[old_oid]
            if new_oid:
                data["outline_id"] = new_oid
            db.add(Chapter(project_id=new_proj.id, **data))
    await db.flush()

    add_all(Foreshadow, req.get("foreshadows", []))
    add_all(Career, req.get("careers", []))
    # 角色职业关联：mumu 格式用 name，需映射为 id
    if req.get("character_careers"):
        career_name_map = {}
        careers_db = (
            (await db.execute(select(Career).where(Career.project_id == new_proj.id)))
            .scalars().all()
        )
        career_name_map = {c.name: c.id for c in careers_db if c.name}
        _seen_char_careers = set()
        for it in req.get("character_careers", []):
            if isinstance(it, dict):
                char_name = it.get("character_name", "")
                career_name = it.get("career_name", "")
                name_key = (char_name, career_name)
                if name_key in _seen_char_careers or not (char_name and career_name):
                    continue
                _seen_char_careers.add(name_key)
                data = {k: v for k, v in it.items() if k != "id" and k != "character_name" and k != "career_name"}
                c_obj = char_name_map.get(char_name)
                career_id = career_name_map.get(career_name)
                if c_obj and career_id:
                    data["character_id"] = c_obj.id
                    data["career_id"] = career_id
                    db.add(CharacterCareer(project_id=new_proj.id, **data))
    add_all(Item, req.get("items", []))
    add_all(Location, req.get("locations", []))
    await db.flush()

    # 组织成员表：需要 name→id 映射（mumu 格式用 name，原生格式用 id）
    org_name_map = {}
    if req.get("organization_members"):
        orgs_db = (
            (await db.execute(select(Organization).where(Organization.project_id == new_proj.id)))
            .scalars().all()
        )
        org_name_map = {o.name: o.id for o in orgs_db if o.name}
    # 先清除该项目已有的旧组织成员，避免重复导入时 UNIQUE 冲突
    await db.execute(delete(OrganizationMember).where(OrganizationMember.project_id == new_proj.id))
    _seen_org_members = set()
    for it in req.get("organization_members", []):
        if isinstance(it, dict):
            org_name = it.get("organization_name", "")
            char_name = it.get("character_name", "")
            # 按原始 name 去重（在 ID 映射之前）
            name_key = (org_name, char_name)
            if name_key in _seen_org_members or not (org_name and char_name):
                continue
            _seen_org_members.add(name_key)
            data = {k: v for k, v in it.items() if k != "id"}
            # name → id（mumu）
            if "organization_name" in data:
                oid = org_name_map.get(data.pop("organization_name"))
                if oid:
                    data["organization_id"] = oid
            if "character_name" in data:
                obj = char_name_map.get(data.pop("character_name"))
                if obj:
                    data["character_id"] = obj.id
            if data.get("organization_id") and data.get("character_id"):
                db.add(OrganizationMember(project_id=new_proj.id, **data))

    add_all(StoryMemory, req.get("memories", []))
    add_all(PlotAnalysis, req.get("analyses", []))
    await db.commit()
    return {"id": new_proj.id, "title": new_proj.title}


# ========== 思考模式设置 ==========

THINKING_MODES_DEFAULTS = {
    "world": {"enabled": False, "reasoning_effort": "high", "temperature": None},
    "character": {"enabled": False, "reasoning_effort": "high", "temperature": None},
    "outline": {"enabled": False, "reasoning_effort": "high", "temperature": None},
    "expand": {"enabled": False, "reasoning_effort": "low", "temperature": None},
    "chapter": {"enabled": False, "reasoning_effort": "none", "temperature": None},
    "polish": {"enabled": False, "reasoning_effort": "none", "temperature": None},
    "analysis": {"enabled": False, "reasoning_effort": "high", "temperature": None},
}


@router.get("/{project_id}/thinking-modes")
async def get_thinking_modes(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    proj = await get_user_project(db, project_id, user)
    settings = dict(proj.settings or {})
    modes = settings.get("thinking_modes", THINKING_MODES_DEFAULTS)
    # 补全新模式默认值
    for k, v in THINKING_MODES_DEFAULTS.items():
        if k not in modes:
            modes[k] = v
    return {"modes": modes}


@router.put("/{project_id}/thinking-modes")
async def update_thinking_modes(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    proj = await get_user_project(db, project_id, user)
    settings = dict(proj.settings or {})
    settings["thinking_modes"] = req.get("modes", THINKING_MODES_DEFAULTS)
    proj.settings = settings
    await db.commit()
    return {"ok": True}
