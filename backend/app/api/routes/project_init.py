"""项目初始化后台任务：异步生成世界观/角色/大纲。

对标 MuMuAINovel 的后台批量生成。用户提交后立即返回任务ID，
后端 asyncio.create_task 执行，前端轮询 /status 查进度。
"""
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def _safe_skill_call(engine, ai_client, skill_name, context, label="步骤"):
    """带连接重试的 skill 调用（解决后台任务 Connection error）。

    注意：execute_skill 内部已含 chat_json_retry（3次重试），
    这里只额外重试 1 次处理偶发的进程级错误，避免 3×3=9 次超长等待。
    """
    last_err = None
    for attempt in range(2):  # 最多 2 次（含 execute_skill 内的 3 次 JSON 重试）
        try:
            result = await engine.execute_skill(skill_name, ai_client, context)
            if not result.get("error"):
                return result, None
            last_err = result.get("error")
        except Exception as e:
            last_err = str(e)
        if attempt == 0:
            await asyncio.sleep(3)  # 仅重试 1 次时等 3 秒
    return None, f"{label}失败: {last_err}"


async def _safe_chat_json(ai_client, messages, label="步骤"):
    """带连接重试的直接 chat_json 调用。

    注意：chat_json_retry 内部已重试 3 次，这里只额外 1 次。
    """
    last_err = None
    for attempt in range(2):
        try:
            result = await ai_client.chat_json_retry(messages=messages, temperature=0.7, max_retries=3)
            if not result.get("error") and result.get("json"):
                return result, None
            last_err = result.get("error") or "返回为空"
        except Exception as e:
            last_err = str(e)
        if attempt == 0:
            await asyncio.sleep(3)
    return None, f"{label}失败: {last_err}"

from app.core.database import get_db, async_session
from app.core.auth import get_current_user
from app.models.project import Project
from app.models.project_init_task import ProjectInitTask
from app.skills.engine import SkillEngine
from app.core.ai_client import AIClient

router = APIRouter(prefix="/api/projects", tags=["项目初始化"])


async def _run_init_task(task_id: int):
    """后台执行：生成世界观 → 角色 → 大纲。用独立 session（不阻塞请求）。"""
    async with async_session() as db:
        task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
        if not task:
            return
        pid = task.project_id
        proj = (await db.execute(select(Project).where(Project.id == pid))).scalar_one_or_none()
        if not proj:
            task.status = "failed"; task.error = "项目不存在"
            await db.commit(); return

        task.status = "running"
        task.status_message = "开始生成..."
        await db.commit()

        engine = SkillEngine(db, task.user_id)
        ai_client = await AIClient.from_user_config(db, task.user_id)
        errors = []

        # 步骤1：核心世界观（走提示词模板系统，用户可自定义）
        try:
            task.status_message = "生成核心世界观..."
            task.progress = 10
            await db.commit()
            result, werr = await _safe_skill_call(engine, ai_client, "world_core_generate", {
                "genre": proj.genre or "网文", "title": proj.title, "synopsis": proj.synopsis or "暂无",
            }, "世界观")
            if werr:
                errors.append(werr)
            else:
                data = result.get("json") or {}
                if isinstance(data, dict):
                    proj.world_time_period = str(data.get("world_time_period", ""))[:2000]
                    proj.world_location = str(data.get("world_location", ""))[:2000]
                    proj.world_atmosphere = str(data.get("world_atmosphere", ""))[:2000]
                    proj.world_rules = str(data.get("world_rules", ""))[:2000]
                    await db.commit()
                task.world_done = 1
            task.progress = 20
            await db.commit()

            # 同时生成详细世界设定条目（地理/历史/势力等，200-400字/条）
            try:
                from app.models.world import WorldSetting
                detail_result, derr = await _safe_skill_call(engine, ai_client, "world_detail_generate", {
                    "genre": proj.genre or "网文", "title": proj.title,
                    "world_info": f"时间={proj.world_time_period}\n地点={proj.world_location}\n规则={proj.world_rules}",
                }, "详细设定")
                if not derr and detail_result:
                    items = detail_result.get("json") or []
                    if isinstance(items, list):
                        for item in items[:10]:
                            if isinstance(item, dict) and item.get("name"):
                                db.add(WorldSetting(project_id=pid,
                                    name=str(item.get("name",""))[:100],
                                    category=str(item.get("category","其他"))[:50],
                                    content=str(item.get("content",""))[:2000]))
                        await db.commit()
            except Exception as e:
                errors.append(f"详细设定: {e}")

            task.progress = 30
            await db.commit()
        except Exception as e:
            errors.append(f"世界观: {e}")

        # 步骤2：组织/势力（用直接 chat 生成多个，不走单个 skill）
        try:
            task.status_message = "生成组织势力..."
            task.progress = 42
            await db.commit()
            from app.models.organization import Organization
            org_result, oerr = await _safe_skill_call(engine, ai_client, "organization_generate", {
                "title": proj.title, "genre": proj.genre or "网文",
                "world_info": f"{proj.world_location or ''} {proj.world_rules or ''}",
                "user_prompt": f"请为《{proj.title}》生成3-5个组织势力。",
            }, "组织")
            if oerr:
                errors.append(oerr)
            elif org_result:
                orgs_data = org_result.get("json") or []
                if not isinstance(orgs_data, list):
                    orgs_data = [orgs_data] if isinstance(orgs_data, dict) else []
                for item in orgs_data[:6]:
                    if isinstance(item, dict) and item.get("name"):
                        pv = item.get("power_value", item.get("power_level", 50))
                        try: pv = int(pv)
                        except: pv = 50
                        db.add(Organization(project_id=pid,
                            name=str(item.get("name",""))[:100],
                            org_type=str(item.get("org_type", item.get("organization_type", item.get("type",""))))[:50],
                            description=str(item.get("description", item.get("background","")))[:2000],
                            power_value=pv,
                            location=str(item.get("location",""))[:200],
                            motto=str(item.get("motto",""))[:200],
                            color=str(item.get("color",""))[:20]))
                await db.commit()
                task.org_done = 1
        except Exception as e:
            errors.append(f"组织: {e}")

        # 步骤2.5：职业体系
        try:
            task.status_message = "生成职业体系..."
            task.progress = 48
            await db.commit()
            from app.models.career import Career
            career_result, cerr2 = await _safe_skill_call(engine, ai_client, "career_system_generation", {
                "title": proj.title, "genre": proj.genre or "网文",
                "world_info": f"规则：{proj.world_rules or ''}",
                "user_prompt": f"请为《{proj.title}》生成职业体系。",
            }, "职业")
            if cerr2:
                errors.append(cerr2)
            elif career_result:
                careers_data = career_result.get("json") or []
                if not isinstance(careers_data, list):
                    careers_data = [careers_data] if isinstance(careers_data, dict) else []
                for item in careers_data[:8]:
                    if isinstance(item, dict) and item.get("name"):
                        db.add(Career(project_id=pid,
                            name=str(item.get("name",""))[:100],
                            career_type=str(item.get("career_type","main"))[:20],
                            category=str(item.get("category",""))[:50],
                            description=str(item.get("description",""))[:2000],
                            stages=item.get("stages",[]),
                            abilities=item.get("abilities",[])))
                await db.commit()
        except Exception as e:
            errors.append(f"职业: {e}")

        # 步骤3：角色
        try:
            task.status_message = "生成角色..."
            task.progress = 55
            await db.commit()
            result, cerr = await _safe_skill_call(engine, ai_client, "characters_batch_generation", {
                "genre": proj.genre or "网文", "title": proj.title,
                "synopsis": proj.synopsis or "暂无简介", "count": "5",
                "existing_characters": "暂无", "world_info": f"{proj.world_location or ''} {proj.world_rules or ''}",
                "user_prompt": "请生成5个角色",
            }, "角色")
            if cerr:
                errors.append(cerr)
            elif result:
                from app.models.character import Character
                chars_data = result.get("json") or []
                added = 0
                if isinstance(chars_data, list):
                    # 预查已有角色名（去重）
                    existing_names = set()
                    existing_chars = (await db.execute(select(Character.name).where(Character.project_id == pid))).all()
                    existing_names = {r[0] for r in existing_chars}
                    for item in chars_data:
                        if not isinstance(item, dict) or not item.get("name"):
                            continue
                        char_name = str(item.get("name", "")).strip()
                        # 跳过组织（AI 可能把组织也返回了）
                        if item.get("is_organization") or item.get("is_org"):
                            continue
                        # 跳过重复
                        if char_name in existing_names:
                            continue
                        existing_names.add(char_name)
                        # 字段映射：AI 可能用不同字段名，统一映射到模型字段
                        db.add(Character(project_id=pid,
                                name=str(item.get("name", ""))[:100],
                                role=str(item.get("role", item.get("character_role", "配角")))[:100],
                                gender=str(item.get("gender", ""))[:50],
                                age=str(item.get("age", ""))[:50],
                                appearance=str(item.get("appearance", item.get("look", "")))[:2000],
                                personality=str(item.get("personality", item.get("character_traits", "")))[:2000],
                                background=str(item.get("background", item.get("history", "")))[:2000],
                                # 成长经历
                                growth_experience=str(item.get("growth_experience", item.get("growth", item.get("backstory", ""))))[:2000],
                                # 能力
                                ability=str(item.get("ability", item.get("abilities", item.get("skills", ""))))[:2000],
                                # 故事目标（映射 goal → story_goal）
                                story_goal=str(item.get("story_goal", item.get("goal", item.get("core_goal", ""))))[:2000],
                                # 动机（映射 pressure_point/motivation → motivation）
                                motivation=str(item.get("motivation", item.get("internal_motivation", item.get("driving_force", ""))))[:2000],
                                # 弱点（映射 pressure_point/weakness → weakness）
                                weakness=str(item.get("weakness", item.get("pressure_point", item.get("vulnerability", ""))))[:2000],
                                # 身份
                                identity=str(item.get("identity", item.get("social_role", "")))[:200],
                                # 职业
                                occupation=str(item.get("occupation", item.get("profession", item.get("career", ""))))[:200],
                                # 说话风格
                                speech_style=str(item.get("speech_style", item.get("dialogue_style", "")))[:200],
                                # 变化
                                arc_type=str(item.get("arc_type", item.get("character_arc", "")))[:200],
                                character_change=str(item.get("character_change", item.get("transformation", "")))[:2000],
                        ))
                        added += 1
                    if added:
                        await db.commit()
                        task.characters_done = 1
                        task.status_message = f"已生成 {added} 个角色"
                        await db.commit()
            task.progress = 60
            await db.commit()
        except Exception as e:
            errors.append(f"角色: {e}")

        # 步骤3.5：角色关系图谱（基于已生成的角色，AI 分析两两关系）
        try:
            task.status_message = "生成角色关系..."
            task.progress = 63
            await db.commit()
            from app.models.character import Character, CharacterRelation
            chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
            if len(chars) >= 2:
                char_list = "、".join(f"{c.name}（{c.role or '角色'}）" for c in chars[:10])
                rel_result, rerr = await _safe_skill_call(engine, ai_client, "character_relations_generate", {
                    "title": proj.title, "characters_info": char_list,
                }, "关系图谱")
                if not rerr and rel_result:
                    rels = rel_result.get("json") or []
                    if isinstance(rels, list):
                        name_to_id = {c.name: c.id for c in chars}
                        added_rels = 0
                        for rel in rels:
                            if not isinstance(rel, dict):
                                continue
                            from_name = rel.get("from", "")
                            to_name = rel.get("to", "")
                            from_id = name_to_id.get(from_name)
                            to_id = name_to_id.get(to_name)
                            if from_id and to_id and from_id != to_id:
                                db.add(CharacterRelation(
                                    project_id=pid,
                                    from_character_id=from_id,
                                    to_character_id=to_id,
                                    relation_type=str(rel.get("relation_type", "关系"))[:100],
                                    category=str(rel.get("category", "social"))[:50],
                                    intimacy=int(rel.get("intimacy", 50)) if str(rel.get("intimacy", "50")).lstrip("-").isdigit() else 50,
                                    description=str(rel.get("description", ""))[:500],
                                ))
                                added_rels += 1
                        if added_rels:
                            await db.commit()
                            task.status_message = f"已生成 {added_rels} 条角色关系"
                            await db.commit()
        except Exception as e:
            errors.append(f"关系: {e}")

        # 步骤3.6：地点地图
        try:
            task.status_message = "生成地点地图..."
            task.progress = 66
            await db.commit()
            from app.models.location import Location
            loc_result, lerr = await _safe_skill_call(engine, ai_client, "locations_generate", {
                "title": proj.title, "world_info": f"{proj.world_location or ''} {proj.synopsis or ''}",
            }, "地点")
            if not lerr and loc_result:
                locs = loc_result.get("json") or []
                if isinstance(locs, list):
                    for loc in locs[:10]:
                        if isinstance(loc, dict) and loc.get("name"):
                            db.add(Location(
                                project_id=pid,
                                name=str(loc.get("name", ""))[:100],
                                location_type=str(loc.get("location_type", "城市"))[:50],
                                description=str(loc.get("description", ""))[:2000],
                                atmosphere=str(loc.get("atmosphere", ""))[:500],
                                importance=str(loc.get("importance", "normal"))[:20],
                                source="ai",
                            ))
                    await db.commit()
        except Exception as e:
            errors.append(f"地点: {e}")

        # 步骤3.7：物品道具
        try:
            task.status_message = "生成物品道具..."
            task.progress = 70
            await db.commit()
            from app.models.item import Item
            item_result, ierr = await _safe_skill_call(engine, ai_client, "items_generate", {
                "title": proj.title, "world_info": f"规则：{proj.world_rules or ''} 简介：{proj.synopsis or ''}",
            }, "物品")
            if not ierr and item_result:
                items = item_result.get("json") or []
                if isinstance(items, list):
                    for it in items[:10]:
                        if isinstance(it, dict) and it.get("name"):
                            db.add(Item(
                                project_id=pid,
                                name=str(it.get("name", ""))[:100],
                                category=str(it.get("category", "装备"))[:50],
                                rarity=str(it.get("rarity", "common"))[:20],
                                item_type=str(it.get("item_type", ""))[:50],
                                description=str(it.get("description", ""))[:2000],
                                is_key_item=1 if it.get("is_key_item") else 0,
                                status="stored",
                                source="ai",
                            ))
                    await db.commit()
        except Exception as e:
            errors.append(f"物品: {e}")

        # 步骤4：大纲
        try:
            task.status_message = "生成大纲..."
            task.progress = 75
            await db.commit()
            from app.models.outline import Outline
            from app.models.chapter import Chapter
            from app.models.world import WorldSetting
            from app.models.character import Character
            worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == pid))).scalars().all()
            chars = (await db.execute(select(Character).where(Character.project_id == pid))).scalars().all()
            world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or f"{proj.world_location} {proj.world_rules}"
            chars_info = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"
            # 大纲用完整 skill 模板（模型支持大上下文）
            result, oerr = await _safe_skill_call(engine, ai_client, "outline_create", {
                "world_info": world_info, "characters_info": chars_info,
                "synopsis": proj.synopsis or "暂无简介", "chapter_count": "10",
                "user_prompt": f"请为《{proj.title}》生成10章大纲",
            }, "大纲")
            if oerr:
                errors.append(oerr)
            elif result:
                outlines_data = result.get("json") or []
                added = 0
                created_outline_objs = []
                if isinstance(outlines_data, list):
                    for idx, item in enumerate(outlines_data):
                        if isinstance(item, dict):
                            # 确保 chapter_number 连续（AI 可能不返回或乱序）
                            ch_num = item.get("chapter_number")
                            if not isinstance(ch_num, int) or ch_num < 1:
                                ch_num = idx + 1
                            o = Outline(
                                project_id=pid,
                                chapter_number=ch_num,
                                title=str(item.get("title", f"第{ch_num}章"))[:200],
                                summary=str(item.get("summary", ""))[:2000],
                                key_points=item.get("key_points", []) if isinstance(item.get("key_points"), list) else [],
                                emotion=str(item.get("emotion", ""))[:100],
                                goal=str(item.get("goal", ""))[:200],
                                structure=item,
                            )
                            db.add(o)
                            created_outline_objs.append(o)
                            added += 1
                    if added:
                        await db.flush()  # 拿到 outline.id

                        # 1对1模式：自动为每条大纲创建对应章节
                        if (proj.outline_mode or "one_to_one") == "one_to_one":
                            for o in created_outline_objs:
                                # 检查是否已存在同章号的章节
                                existing_ch = (await db.execute(
                                    select(Chapter).where(
                                        Chapter.project_id == pid,
                                        Chapter.chapter_number == o.chapter_number,
                                    )
                                )).scalars().first()
                                if existing_ch:
                                    continue
                                ch = Chapter(
                                    project_id=pid,
                                    chapter_number=o.chapter_number,
                                    title=o.title,
                                    summary=o.summary[:200] if o.summary else "",
                                    status="draft",
                                    outline_id=None,
                                    sub_index=1,
                                    generation_mode="one_to_one",
                                )
                                db.add(ch)
                        await db.commit()
                        task.outline_done = 1
                        task.status_message = f"已生成 {added} 章大纲"
                        await db.commit()
            task.progress = 100
            await db.commit()
        except Exception as e:
            errors.append(f"大纲: {e}")

        task.status = "completed" if not errors else "completed"
        task.status_message = "生成完成" + (f"（部分失败：{'; '.join(errors)}」" if errors else "")
        task.progress = 100
        task.updated_at = datetime.utcnow()
        await db.commit()


@router.post("/{project_id}/init-task")
async def create_init_task(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """提交项目初始化后台任务，立即返回任务ID。"""
    proj = (await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, "项目不存在")
    task = ProjectInitTask(project_id=project_id, user_id=user.id, task_type="init",
                           status="pending", status_message="排队中...")
    db.add(task)
    await db.commit()
    await db.refresh(task)
    # 异步执行（不阻塞请求）
    asyncio.create_task(_run_init_task(task.id))
    return {"task_id": task.id, "project_id": project_id, "status": "pending"}


@router.get("/init-task/{task_id}/status")
async def get_init_task_status(task_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """查询初始化任务进度。"""
    task = (await db.execute(select(ProjectInitTask).where(ProjectInitTask.id == task_id))).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()
