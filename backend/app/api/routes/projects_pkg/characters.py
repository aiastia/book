"""角色：CRUD / 生成 / 批量生成 / 自动分析 / 自动生成"""

import json

from app.api.routes.projects_pkg.base import *
from app.core.database import async_session

router = make_router()


async def _sync_org_membership(
    db: AsyncSession, project_id: int, character_id: int, organization_id: int | None
):
    """统一组织关系：当角色设了 organization_id 时，自动同步到 OrganizationMember 表。

    改为非破坏性：仅 upsert 主组织记录，不删除角色在其他组织中的成员关系。
    角色可以通过组织管理页面属于多个组织。
    """
    from sqlalchemy import delete as sa_delete

    from app.models.organization_member import OrganizationMember

    # 清理该角色在此主组织下的旧成员记录（如果有）
    if organization_id:
        await db.execute(
            sa_delete(OrganizationMember).where(
                OrganizationMember.project_id == project_id,
                OrganizationMember.character_id == character_id,
                OrganizationMember.organization_id == organization_id,
            )
        )
        # 用角色定位作为默认职位提示
        char = await db.scalar(select(Character.role).where(Character.id == character_id))
        default_position = (
            "" if (char or "").strip() in ("主角", "配角", "反派", "路人", "") else (char or "")
        )
        member = OrganizationMember(
            project_id=project_id,
            organization_id=organization_id,
            character_id=character_id,
            position=default_position,
            rank=5,
            loyalty=50,
            contribution=20,
            status="active",
            source="character_fk",
        )
        db.add(member)
        await db.flush()
    # 如果 organization_id 被清空，删除该角色的所有 OrganizationMember 记录中被标记为 character_fk 来源的
    # （保留从组织页面手动添加的记录）
    else:
        await db.execute(
            sa_delete(OrganizationMember).where(
                OrganizationMember.project_id == project_id,
                OrganizationMember.character_id == character_id,
                OrganizationMember.source == "character_fk",
            )
        )


def _normalize_sub_occupations(data: dict) -> str:
    """从 AI 返回中提取副职业，归一为分号分隔字符串。"""
    raw = data.get("sub_careers") or data.get("secondary_occupations") or []
    if isinstance(raw, str):
        parts = [
            p.strip() for p in raw.replace("，", ";").replace(",", ";").split(";") if p.strip()
        ]
        return ";".join(parts)[:500]
    if isinstance(raw, list):
        out = []
        for o in raw:
            if isinstance(o, str) and o.strip():
                out.append(o.strip())
            elif isinstance(o, dict):
                n = o.get("name") or o.get("main_career")
                if n:
                    out.append(str(n).strip())
        return ";".join(out)[:500]
    return ""


@router.get("/{project_id}/characters")
async def list_characters(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    result = await db.execute(select(Character).where(Character.project_id == project_id))
    return [
        {
            "id": c.id,
            "name": c.name,
            "role": c.role,
            "gender": c.gender,
            "age": c.age,
            "appearance": c.appearance,
            "personality": c.personality,
            "background": c.background,
            "growth_experience": c.growth_experience,
            "ability": c.ability,
            "story_goal": c.story_goal,
            "motivation": c.motivation,
            "weakness": c.weakness,
            "arc_type": c.arc_type,
            "character_change": c.character_change,
            "speech_style": c.speech_style,
            "status": c.status,
            "mental_state": c.mental_state,
            "tags": c.tags,
            "main_career_id": c.main_career_id,
            "main_career_stage": c.main_career_stage,
            "main_career_stage_desc": c.main_career_stage_desc or "",
            "sub_careers": c.sub_careers or [],
            "organization_id": c.organization_id,
        }
        for c in result.scalars().all()
    ]


@router.post("/{project_id}/characters")
async def create_character(
    project_id: int,
    req: CharacterCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    char = Character(project_id=project_id, **req.model_dump())
    db.add(char)
    await db.commit()
    await db.refresh(char)
    await _sync_org_membership(db, project_id, char.id, char.organization_id)
    return {"id": char.id, "name": char.name}


@router.post("/{project_id}/characters/generate")
async def generate_character(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """AI 生成单个角色并存库"""
    proj = await get_user_project(db, project_id, user)
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
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    existing_chars = ", ".join([f"{c.name}({c.role})" for c in chars]) or "暂无"

    # 补充职业体系和组织上下文（让 AI 匹配职业体系中的 main_career / organization_memberships）
    from app.models.career import Career
    from app.models.organization import Organization

    all_careers = (
        (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    )
    career_info = "、".join(c.name for c in all_careers[:8]) if all_careers else "暂无"
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    org_info = "、".join(o.name for o in orgs[:10]) if orgs else "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "character_generate",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "world_info": world_info,
            "role_type": req.get("role_type", "配角"),
            "existing_chars": existing_chars,
            "user_prompt": (
                f"请生成一个{req.get('role_type', '配角')}角色。{req.get('extra', '')}\n"
                f"【重要】职业（main_career）务必从已有职业体系中选择：{career_info}\n"
                f"【重要】所属组织（organization_memberships）务必从已有组织中选择：{org_info}。无组织则返回空数组 []"
            ),
        },
    )
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
    # 映射职业体系（单角色生成也需处理）
    occ_raw = str(data.get("main_career") or data.get("occupation", ""))
    if occ_raw:
        from app.models.career import Career

        all_careers = (
            (await db.execute(select(Career).where(Career.project_id == project_id)))
            .scalars()
            .all()
        )
        for c_obj in all_careers:
            if occ_raw in c_obj.name or c_obj.name in occ_raw:
                char.main_career_id = c_obj.id
                if not char.main_career_stage_desc:
                    stages = (c_obj.stages or []) if isinstance(c_obj.stages, list) else []
                    if stages:
                        char.main_career_stage_desc = stages[0].get("name", "")
                db.add(char)
                await db.commit()
                break

    # 单个角色生成后：若项目已有≥2个角色，自动建立关系（让关系图谱能看到新角色）
    try:
        if len(chars) + 1 >= 2:
            from app.api.routes.projects_pkg.relations import auto_rebuild_relations as _rebuild

            await _rebuild(project_id, db, user)
    except Exception as e:
        print(f"[characters] 单角色生成后建关系失败（忽略）: {e}")

    return {
        "id": char.id,
        "name": char.name,
        "role": char.role,
        "gender": char.gender,
        "appearance": char.appearance,
        "personality": char.personality,
        "background": char.background,
        "growth_experience": char.growth_experience,
        "ability": char.ability,
        "story_goal": char.story_goal,
        "motivation": char.motivation,
        "weakness": char.weakness,
        "arc_type": char.arc_type,
        "character_change": char.character_change,
        "speech_style": char.speech_style,
        "status": char.status,
        "mental_state": char.mental_state,
        "main_career_id": char.main_career_id,
        "main_career_stage": char.main_career_stage,
        "sub_careers": char.sub_careers or [],
        "organization_id": char.organization_id,
    }


@router.put("/{project_id}/characters/{character_id}")
async def update_character(
    project_id: int,
    character_id: int,
    req: CharacterCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    c = (
        await db.execute(
            select(Character).where(
                Character.id == character_id, Character.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "角色不存在")
    for key, value in req.model_dump().items():
        setattr(c, key, value)
    await db.commit()
    await _sync_org_membership(db, project_id, character_id, c.organization_id)
    return {"ok": True}


@router.get("/{project_id}/characters/{character_id}/organizations")
async def get_character_organizations(
    project_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取角色所属的所有组织（从 OrganizationMember 表）"""
    await get_user_project(db, project_id, user)
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember

    members = (
        (
            await db.execute(
                select(OrganizationMember).where(
                    OrganizationMember.project_id == project_id,
                    OrganizationMember.character_id == character_id,
                )
            )
        )
        .scalars()
        .all()
    )
    org_ids = [m.organization_id for m in members]
    orgs = []
    if org_ids:
        org_rows = (
            (await db.execute(select(Organization).where(Organization.id.in_(org_ids))))
            .scalars()
            .all()
        )
        org_map = {o.id: o for o in org_rows}
        for m in members:
            o = org_map.get(m.organization_id)
            if o:
                orgs.append({"id": o.id, "name": o.name, "position": m.position or ""})
    return orgs


@router.delete("/{project_id}/characters/{character_id}")
async def delete_character(
    project_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    c = (
        await db.execute(
            select(Character).where(
                Character.id == character_id, Character.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "角色不存在")
    # 清理组织成员记录
    from sqlalchemy import delete as sa_delete

    from app.models.organization_member import OrganizationMember

    await db.execute(
        sa_delete(OrganizationMember).where(
            OrganizationMember.project_id == project_id,
            OrganizationMember.character_id == character_id,
        )
    )
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/characters/batch-generate")
async def batch_generate_characters(
    project_id: int,
    req: BatchCharacterRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """批量生成角色并存库"""
    proj = await get_user_project(db, project_id, user)
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
    existing_chars = (
        "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    )
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"

    engine, ai_client = await make_engine_and_client(db, user.id)

    # 获取已有职业体系和组织列表（传给 AI + 后续匹配）
    from app.models.career import Career
    from app.models.organization import Organization

    all_careers = (
        (await db.execute(select(Career).where(Career.project_id == project_id))).scalars().all()
    )
    career_info = "、".join(c.name for c in all_careers[:8]) if all_careers else "暂无"
    orgs = (
        (await db.execute(select(Organization).where(Organization.project_id == project_id)))
        .scalars()
        .all()
    )
    org_info = "、".join(o.name for o in orgs[:10]) if orgs else "暂无"

    result = await engine.execute_skill(
        "characters_batch_generation",
        ai_client,
        {
            "genre": proj.genre or "网文",
            "title": proj.title,
            "synopsis": proj.synopsis or "暂无简介",
            "count": str(req.count),
            "existing_characters": existing_chars,
            "world_info": world_info,
            "user_prompt": f"""请生成{req.count}个角色。{req.requirements}
【重要】主职业和副职业务必从已有职业体系中选择：{career_info}
【重要】所属组织务必从已有组织中选择：{org_info}。无组织则 organization_memberships 返回空数组 []""",
        },
    )
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
        db.add(
            Character(
                project_id=project_id,
                name=str(item.get("name", ""))[:100],
                role=str(
                    item.get("role", item.get("role_type", item.get("character_role", "配角")))
                )[:100],
                gender=str(item.get("gender", ""))[:50],
                age=str(item.get("age", ""))[:50],
                identity=str(item.get("identity", ""))[:200],
                appearance=str(item.get("appearance", ""))[:2000],
                personality=str(item.get("personality", item.get("character_traits", "")))[:2000],
                background=str(item.get("background", ""))[:2000],
                growth_experience=str(
                    item.get("growth_experience", item.get("growth", item.get("backstory", "")))
                )[:2000],
                ability=str(item.get("ability", item.get("abilities", item.get("skills", ""))))[
                    :2000
                ],
                story_goal=str(item.get("story_goal", item.get("goal", item.get("core_goal", ""))))[
                    :2000
                ],
                motivation=str(
                    item.get(
                        "motivation", item.get("internal_motivation", item.get("driving_force", ""))
                    )
                )[:2000],
                weakness=str(
                    item.get("weakness", item.get("pressure_point", item.get("vulnerability", "")))
                )[:2000],
                speech_style=str(item.get("speech_style", item.get("dialogue_style", "")))[:200],
                arc_type=str(item.get("arc_type", item.get("character_arc", "")))[:200],
                character_change=str(item.get("character_change", item.get("transformation", "")))[
                    :2000
                ],
                tags=item.get("traits", []) if isinstance(item.get("traits"), list) else [],
            )
        )
        created.append(item)
    await db.flush()  # 拿到 char.id

    # 匹配职业体系和组织（复用 _step_characters 的逻辑）
    if all_careers:
        main_career_map = {c.name: c.id for c in all_careers if c.career_type == "main"}
        sub_career_map = {c.name: c.id for c in all_careers if c.career_type == "sub"}
        all_career_map = {c.name: c.id for c in all_careers}
        career_by_id = {c.id: c for c in all_careers}

        def _default_stage(career_obj):
            """根据职业的阶段列表返回合理的默认境界名。
            不再只是取第一个——如果 AI 已通过批量生成分配了 stage_desc 就用它，
            否则取第二个阶段（第一个通常是入门，第二个更有辨识度）。
            """
            stages = career_obj.stages or []
            if len(stages) >= 2:
                return stages[1].get("name", stages[0].get("name", ""))
            return stages[0].get("name", "") if stages else ""

        for item in chars_data:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            char_name = str(item.get("name", "")).strip()
            # 找对应的 Character 对象
            char_obj = (
                (
                    await db.execute(
                        select(Character).where(
                            Character.project_id == project_id, Character.name == char_name
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not char_obj:
                continue
            # 主职业匹配：只从 main 类型职业中选
            occ_raw = str(item.get("main_career") or item.get("main_career", ""))
            occ_parts = [
                p.strip()
                for p in occ_raw.replace("/", ",").replace("、", ",").split(",")
                if p.strip()
            ]
            for occ in occ_parts:
                if not char_obj.main_career_id:
                    if occ in main_career_map:
                        char_obj.main_career_id = main_career_map[occ]
                    else:
                        for cname, cid in main_career_map.items():
                            if occ in cname or cname in occ:
                                char_obj.main_career_id = cid
                                break
                if char_obj.main_career_id:
                    ai_stage = str(item.get("main_career_stage", "")).strip()
                    if ai_stage:
                        char_obj.main_career_stage_desc = ai_stage
                    elif not char_obj.main_career_stage_desc:
                        c_obj = career_by_id.get(char_obj.main_career_id)
                        if c_obj:
                            char_obj.main_career_stage_desc = _default_stage(c_obj)
            # 副职业匹配
            sub_names = set()
            subs_raw = item.get("sub_careers") or item.get("sub_careers") or []
            if isinstance(subs_raw, str):
                subs_raw = [
                    s.strip()
                    for s in subs_raw.replace("，", ",").replace("/", ",").split(",")
                    if s.strip()
                ]
            for sn in subs_raw:
                sub_names.add(str(sn).strip())
            for occ in occ_parts:
                if (
                    not char_obj.main_career_id
                    or all_career_map.get(occ) != char_obj.main_career_id
                ):
                    sub_names.add(occ)
            ai_sub_stages = item.get("sub_career_stages") or []
            if isinstance(ai_sub_stages, str):
                ai_sub_stages = [s.strip() for s in ai_sub_stages.split(",") if s.strip()]
            sub_list = []
            for sn in sub_names:
                cid = None
                cname = sn
                if sn in sub_career_map:
                    cid = sub_career_map[sn]
                elif sn in all_career_map:
                    cid = all_career_map[sn]
                else:
                    for cn, ci in all_career_map.items():
                        if sn in cn or cn in sn:
                            cid = ci
                            cname = cn
                            break
                if cid and cid != char_obj.main_career_id:
                    # 找对应的 AI 境界
                    stage = ""
                    sub_names_list = list(sub_names)
                    idx = sub_names_list.index(sn) if sn in sub_names_list else -1
                    if 0 <= idx < len(ai_sub_stages):
                        stage = str(ai_sub_stages[idx]).strip()
                    if not stage:
                        c_obj = career_by_id.get(cid)
                        if c_obj:
                            stage = _default_stage(c_obj)
                    sub_list.append({"career_id": cid, "name": cname, "stage_desc": stage})
            char_obj.sub_careers = sub_list

    # 组织匹配
    if orgs:
        org_name_to_id = {o.name: o.id for o in orgs}
        for item in chars_data:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            char_name = str(item.get("name", "")).strip()
            char_obj = (
                (
                    await db.execute(
                        select(Character).where(
                            Character.project_id == project_id, Character.name == char_name
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not char_obj:
                continue
            memberships = item.get("organization_memberships", [])
            if isinstance(memberships, str):
                memberships = [memberships]
            for org_name in memberships:
                org_name = str(org_name).strip()
                org_id = org_name_to_id.get(org_name)
                if not org_id:
                    for on, oid in org_name_to_id.items():
                        if org_name in on or on in org_name:
                            org_id = oid
                            break
                if org_id:
                    char_obj.organization_id = org_id
                    # 同步到 OrganizationMember 表（统一真相来源）
                    await _sync_org_membership(db, project_id, char_obj.id, org_id)
                    break  # 只设第一个匹配的组织为主组织

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


@router.post("/{project_id}/characters/batch-generate-async")
async def batch_generate_characters_async(
    project_id: int,
    req: BatchCharacterRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步批量生成角色：立即返回 task_id，后台执行。"""
    await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run_chars(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        await tracker.update(stage="preparing", message="准备生成角色...")
        # 复用同步逻辑（调用 MockReq）
        async with async_session() as task_db:

            class MockReq:
                count = payload["count"]
                requirements = payload.get("requirements", "")

            result = await batch_generate_characters(
                payload["project_id"],
                MockReq(),
                task_db,
                type("U", (), {"id": payload["user_id"]})(),
            )
            if isinstance(result, dict) and result.get("count", 0) > 0:
                await tracker.complete(message=f"生成完成（{result['count']}个角色）")
            else:
                await tracker.fail("角色生成失败")

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="characters",
        title="批量生成角色",
        payload={
            "count": req.count,
            "requirements": req.requirements,
            "project_id": project_id,
            "user_id": user.id,
        },
        runner=_run_chars,
    )
    return {"task_id": task_id}


@router.post("/{project_id}/characters/auto-analysis")
async def auto_analyze_characters(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """自动角色分析：预测是否需要新角色"""
    proj = await get_user_project(db, project_id, user)
    chars = (
        (await db.execute(select(Character).where(Character.project_id == project_id)))
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
    existing_characters = (
        json.dumps(
            [{"name": c.name, "role": c.role, "personality": c.personality} for c in chars],
            ensure_ascii=False,
        )
        if chars
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
        "auto_character_analysis",
        ai_client,
        {
            "chapter_count": str(len(chapters)),
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "existing_outlines": existing_outlines,
            "existing_characters": existing_characters,
            "user_prompt": "请分析当前剧情进展，判断是否需要引入新角色。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/characters/auto-generate")
async def auto_generate_character(
    project_id: int,
    req: AutoCharacterGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """根据分析结果自动生成角色并存库"""
    proj = await get_user_project(db, project_id, user)
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
    existing_characters = (
        "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
    )
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    outline_info = (
        json.dumps(
            [
                {"chapter_number": o.chapter_number, "title": o.title, "summary": o.summary}
                for o in outlines[:10]
            ],
            ensure_ascii=False,
        )
        if outlines
        else "暂无"
    )

    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "auto_character_generation",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "synopsis": proj.synopsis or "暂无简介",
            "existing_characters": existing_characters,
            "world_info": world_info,
            "recent_outlines": outline_info,
            "analysis_result": json.dumps(req.analysis_result, ensure_ascii=False)
            if req.analysis_result
            else "",
            "user_prompt": f"请根据分析结果自动生成一个新角色。{req.specification}",
        },
    )
    check_skill_error(result)
    char_data = result.get("json") or {}
    if not isinstance(char_data, dict):
        raise HTTPException(500, "AI 返回的角色数据格式不正确")
    db.add(
        Character(
            project_id=project_id,
            name=char_data.get("name", ""),
            role=char_data.get("role", "配角"),
            gender=char_data.get("gender", ""),
            age=char_data.get("age", ""),
            appearance=char_data.get("appearance", ""),
            personality=char_data.get("personality", ""),
            background=char_data.get("background", ""),
            ability=char_data.get("ability", ""),
        )
    )
    await db.commit()
    return {"character": char_data}


@router.post("/{project_id}/characters/auto-generate-async")
async def auto_generate_character_async(
    project_id: int,
    req: AutoCharacterGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步自动生成角色：立即返回 task_id，后台执行。"""
    await get_user_project(db, project_id, user)

    from app.services.async_ai_service import submit_async_task

    async def _run_auto_gen(task_id: int, payload: dict):
        from app.services import background_task_service as bgs

        tracker = bgs.TaskProgressTracker(task_id)
        await tracker.update(stage="generating", message="AI 正在生成角色...")
        async with async_session() as task_db:

            class MockReq:
                analysis_result = payload.get("analysis_result", {})
                specification = payload.get("specification", "")

            result = await auto_generate_character(
                payload["project_id"],
                MockReq(),
                task_db,
                type("U", (), {"id": payload["user_id"]})(),
            )
            if isinstance(result, dict):
                await tracker.complete(message="角色生成完成")
            else:
                await tracker.fail("角色生成失败")

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="characters",
        title="自动生成角色",
        payload={
            "project_id": project_id,
            "user_id": user.id,
            "analysis_result": req.analysis_result,
            "specification": req.specification,
        },
        runner=_run_auto_gen,
    )
    return {"task_id": task_id}


@router.post("/{project_id}/characters/sync-org-memberships")
async def sync_org_memberships(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """一键回填：将所有角色已有的 organization_id 同步到 OrganizationMember 表。

    建立统一的角色↔组织关系来源。新创建/编辑的角色会自动同步。
    """
    await get_user_project(db, project_id, user)
    chars = (
        (
            await db.execute(
                select(Character).where(
                    Character.project_id == project_id,
                    Character.organization_id.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    synced = 0
    for c in chars:
        try:
            await _sync_org_membership(db, project_id, c.id, c.organization_id)
            synced += 1
        except Exception:
            pass
    return {"ok": True, "count": synced, "total": len(chars)}


# ============ 角色变化日志 ============


class ChangeLogCreate(BaseModel):
    chapter_number: int
    summary: str = ""
    changed_fields: dict = {}


@router.get("/{project_id}/characters/{character_id}/change-logs")
async def list_change_logs(
    project_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """列出角色的所有变化日志（按章节号升序）"""
    await get_user_project(db, project_id, user)
    from app.models.character_change_log import CharacterChangeLog

    logs = (
        (
            await db.execute(
                select(CharacterChangeLog)
                .where(
                    CharacterChangeLog.project_id == project_id,
                    CharacterChangeLog.character_id == character_id,
                )
                .order_by(CharacterChangeLog.chapter_number.asc())
            )
        )
        .scalars()
        .all()
    )
    return [log.to_dict() for log in logs]


@router.post("/{project_id}/characters/{character_id}/change-logs")
async def create_change_log(
    project_id: int,
    character_id: int,
    req: ChangeLogCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """添加一条角色变化日志，自动保存当前角色完整快照"""
    await get_user_project(db, project_id, user)
    from app.models.character_change_log import CharacterChangeLog

    char = (
        await db.execute(
            select(Character).where(
                Character.id == character_id, Character.project_id == project_id
            )
        )
    ).scalar_one_or_none()
    if not char:
        raise HTTPException(404, "角色不存在")
    # 生成快照：复制当前 Character 的所有字段值
    snapshot = {
        c.name: getattr(char, c.name)
        for c in char.__table__.columns
        if c.name not in ("created_at", "updated_at")
    }
    # JSON 字段转为可序列化形式
    for k, v in snapshot.items():
        if isinstance(v, (list, dict)):
            snapshot[k] = v
    log = CharacterChangeLog(
        project_id=project_id,
        character_id=character_id,
        chapter_number=req.chapter_number,
        changed_fields=req.changed_fields or {},
        snapshot=snapshot,
        summary=req.summary or "",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log.to_dict()


@router.delete("/{project_id}/characters/{character_id}/change-logs/{log_id}")
async def delete_change_log(
    project_id: int,
    character_id: int,
    log_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """删除一条变化日志"""
    await get_user_project(db, project_id, user)
    from app.models.character_change_log import CharacterChangeLog

    log = (
        await db.execute(
            select(CharacterChangeLog).where(
                CharacterChangeLog.id == log_id,
                CharacterChangeLog.project_id == project_id,
                CharacterChangeLog.character_id == character_id,
            )
        )
    ).scalar_one_or_none()
    if not log:
        raise HTTPException(404, "日志不存在")
    await db.delete(log)
    await db.commit()
    return {"ok": True}


async def get_character_state_at_chapter(
    db: AsyncSession, project_id: int, character_id: int, chapter_number: int
) -> dict | None:
    """获取角色在指定章节之前的「当时状态」快照。

    chapter_number 为当前要生成的章节号。返回 < chapter_number 的最新快照。
    无快照则返回 None（调用方用 Character 当前字段作为初始状态）。
    """
    from app.models.character_change_log import CharacterChangeLog

    log = (
        await db.execute(
            select(CharacterChangeLog)
            .where(
                CharacterChangeLog.project_id == project_id,
                CharacterChangeLog.character_id == character_id,
                CharacterChangeLog.chapter_number < chapter_number,
            )
            .order_by(CharacterChangeLog.chapter_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return log.snapshot if log else None
