"""角色：CRUD / 生成 / 批量生成 / 自动分析 / 自动生成"""
import json
from app.api.routes.projects_pkg.base import *


router = make_router()


@router.get("/{project_id}/characters")
async def list_characters(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    result = await db.execute(select(Character).where(Character.project_id == project_id))
    return [{
        "id": c.id, "name": c.name, "role": c.role, "gender": c.gender, "age": c.age,
        "identity": c.identity, "occupation": c.occupation,
        "appearance": c.appearance, "personality": c.personality,
        "background": c.background, "growth_experience": c.growth_experience,
        "ability": c.ability, "story_goal": c.story_goal, "motivation": c.motivation,
        "weakness": c.weakness, "arc_type": c.arc_type, "character_change": c.character_change,
        "speech_style": c.speech_style, "status": c.status, "mental_state": c.mental_state,
        "tags": c.tags,
    } for c in result.scalars().all()]


@router.post("/{project_id}/characters")
async def create_character(project_id: int, req: CharacterCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    char = Character(project_id=project_id, **req.model_dump())
    db.add(char)
    await db.commit()
    await db.refresh(char)
    return {"id": char.id, "name": char.name}


@router.post("/{project_id}/characters/generate")
async def generate_character(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """AI 生成单个角色并存库"""
    await get_user_project(db, project_id, user)
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    existing_chars = ", ".join([f"{c.name}({c.role})" for c in chars]) or "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("character_generate", ai_client, {
        "world_info": world_info, "role_type": req.get("role_type", "配角"),
        "existing_chars": existing_chars,
        "user_prompt": f"请生成一个{req.get('role_type', '配角')}角色。{req.get('extra', '')}",
    })
    check_skill_error(result)
    data = result.get("json") or {}
    if not isinstance(data, dict) or not data.get("name"):
        raise HTTPException(500, "AI 未返回有效角色数据")
    char = Character(
        project_id=project_id,
        name=str(data.get("name", "未命名")),
        role=str(data.get("role", req.get("role_type", "配角")))[:50],
        gender=str(data.get("gender", ""))[:10],
        age=str(data.get("age", ""))[:20],
        identity=str(data.get("identity", ""))[:200],
        occupation=str(data.get("occupation", ""))[:100],
        appearance=str(data.get("appearance", "")),
        personality=str(data.get("personality", "")),
        background=str(data.get("background", "")),
        growth_experience=str(data.get("growth_experience", data.get("growth", ""))),
        ability=str(data.get("ability", "")),
        story_goal=str(data.get("story_goal", data.get("goal", ""))),
        motivation=str(data.get("motivation", "")),
        weakness=str(data.get("weakness", "")),
        arc_type=str(data.get("arc_type", ""))[:50],
        character_change=str(data.get("character_change", data.get("change", ""))),
        speech_style=str(data.get("speech_style", ""))[:200],
        status="alive",
        tags=list(data.get("relationships_suggestions") or []),
    )
    db.add(char)
    await db.commit()
    await db.refresh(char)
    return {
        "id": char.id, "name": char.name, "role": char.role, "gender": char.gender,
        "age": char.age, "identity": char.identity, "occupation": char.occupation,
        "appearance": char.appearance, "personality": char.personality,
        "background": char.background, "growth_experience": char.growth_experience,
        "ability": char.ability, "story_goal": char.story_goal,
        "motivation": char.motivation, "weakness": char.weakness,
        "arc_type": char.arc_type, "character_change": char.character_change,
        "speech_style": char.speech_style, "status": char.status,
        "mental_state": char.mental_state,
    }


@router.put("/{project_id}/characters/{character_id}")
async def update_character(project_id: int, character_id: int, req: CharacterCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    c = (await db.execute(select(Character).where(Character.id == character_id, Character.project_id == project_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "角色不存在")
    for key, value in req.model_dump().items():
        setattr(c, key, value)
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/characters/{character_id}")
async def delete_character(project_id: int, character_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    c = (await db.execute(select(Character).where(Character.id == character_id, Character.project_id == project_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "角色不存在")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/characters/batch-generate")
async def batch_generate_characters(project_id: int, req: BatchCharacterRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """批量生成角色并存库"""
    proj = await get_user_project(db, project_id, user)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    existing_chars = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("characters_batch_generation", ai_client, {
        "genre": proj.genre or "网文", "title": proj.title, "synopsis": proj.synopsis or "暂无简介",
        "count": str(req.count), "existing_characters": existing_chars, "world_info": world_info,
        "user_prompt": f"请为这部{proj.genre or '网文'}批量生成{req.count}个角色。{req.requirements}",
    })
    check_skill_error(result)
    chars_data = result.get("json") or []
    if not isinstance(chars_data, list):
        raise HTTPException(500, "AI 返回的角色格式不正确")
    created = []
    existing_names = {c.name for c in chars}
    for item in chars_data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        char_name = str(item.get("name", "")).strip()
        # 跳过组织（AI 可能把组织当角色返回）
        if item.get("is_organization") or item.get("is_org"):
            continue
        # 跳过重复
        if char_name in existing_names:
            continue
        existing_names.add(char_name)
        db.add(Character(
            project_id=project_id,
            name=str(item.get("name", ""))[:100],
            role=str(item.get("role", item.get("role_type", item.get("character_role", "配角"))))[:100],
            gender=str(item.get("gender", ""))[:50],
            age=str(item.get("age", ""))[:50],
            identity=str(item.get("identity", ""))[:200],
            occupation=str(item.get("occupation", ""))[:200],
            appearance=str(item.get("appearance", ""))[:2000],
            personality=str(item.get("personality", item.get("character_traits", "")))[:2000],
            background=str(item.get("background", ""))[:2000],
            growth_experience=str(item.get("growth_experience", item.get("growth", item.get("backstory", ""))))[:2000],
            ability=str(item.get("ability", item.get("abilities", item.get("skills", ""))))[:2000],
            story_goal=str(item.get("story_goal", item.get("goal", item.get("core_goal", ""))))[:2000],
            motivation=str(item.get("motivation", item.get("internal_motivation", item.get("driving_force", ""))))[:2000],
            weakness=str(item.get("weakness", item.get("pressure_point", item.get("vulnerability", ""))))[:2000],
            speech_style=str(item.get("speech_style", item.get("dialogue_style", "")))[:200],
            arc_type=str(item.get("arc_type", item.get("character_arc", "")))[:200],
            character_change=str(item.get("character_change", item.get("transformation", "")))[:2000],
            tags=item.get("traits", []) if isinstance(item.get("traits"), list) else [],
        ))
        created.append(item)
    await db.commit()

    # 批量生成后自动建立角色关系（≥2 个角色时）
    relations_built = 0
    if len(created) >= 2 or len(chars) >= 2:
        try:
            from app.api.routes.projects_pkg.relations import auto_rebuild_relations as _rebuild
            rel_result = await _rebuild(project_id, db, user)
            relations_built = rel_result.get("count", 0)
        except Exception as e:
            # 关系建立失败不影响角色生成结果
            print(f"[characters] 自动建关系失败（忽略）: {e}")

    return {"characters": created, "count": len(created), "relations_built": relations_built}


@router.post("/{project_id}/characters/auto-analysis")
async def auto_analyze_characters(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """自动角色分析：预测是否需要新角色"""
    proj = await get_user_project(db, project_id, user)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    chapters = (await db.execute(select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number))).scalars().all()
    existing_characters = json.dumps([{"name": c.name, "role": c.role, "personality": c.personality} for c in chars], ensure_ascii=False) if chars else "暂无"
    existing_outlines = json.dumps([{"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary} for o in outlines], ensure_ascii=False) if outlines else "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("auto_character_analysis", ai_client, {
        "chapter_count": str(len(chapters)), "title": proj.title, "genre": proj.genre or "网文",
        "synopsis": proj.synopsis or "暂无简介", "existing_outlines": existing_outlines,
        "existing_characters": existing_characters,
        "user_prompt": "请分析当前剧情进展，判断是否需要引入新角色。",
    })
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/characters/auto-generate")
async def auto_generate_character(project_id: int, req: AutoCharacterGenerateRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """根据分析结果自动生成角色并存库"""
    proj = await get_user_project(db, project_id, user)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    existing_characters = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    outline_info = json.dumps([{"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary} for o in outlines[:10]], ensure_ascii=False) if outlines else "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("auto_character_generation", ai_client, {
        "title": proj.title, "genre": proj.genre or "网文", "synopsis": proj.synopsis or "暂无简介",
        "existing_characters": existing_characters, "world_info": world_info, "recent_outlines": outline_info,
        "analysis_result": json.dumps(req.analysis_result, ensure_ascii=False) if req.analysis_result else "",
        "user_prompt": f"请根据分析结果自动生成一个新角色。{req.specification}",
    })
    check_skill_error(result)
    char_data = result.get("json") or {}
    if not isinstance(char_data, dict):
        raise HTTPException(500, "AI 返回的角色数据格式不正确")
    db.add(Character(
        project_id=project_id,
        name=char_data.get("name", ""), role=char_data.get("role", "配角"),
        gender=char_data.get("gender", ""), age=char_data.get("age", ""),
        appearance=char_data.get("appearance", ""), personality=char_data.get("personality", ""),
        background=char_data.get("background", ""), ability=char_data.get("ability", ""),
        occupation=char_data.get("occupation", ""),
    ))
    await db.commit()
    return {"character": char_data}
