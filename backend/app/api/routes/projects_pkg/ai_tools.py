"""AI 工具：灵感激发 / 去味 / 封面提示词 / 拆书导入 / MCP"""

import json

from app.api.routes.projects_pkg.base import *
from app.core.database import async_session

router = make_router()


# ============ 灵感激发（旧版单次） ============
@router.post("/{project_id}/inspire")
async def inspire(
    project_id: int,
    req: InspireRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "inspire",
        ai_client,
        {
            "idea": req.idea,
            "user_prompt": f"我的想法是：{req.idea}，请帮我拓展成创作方案。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}


# ============ AI 去味/润色 ============
@router.post("/{project_id}/ai-denoising")
async def ai_denoising(
    project_id: int,
    req: AiDenoisingRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """让文本更自然，去除 AI 味"""
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "ai_denoising",
        ai_client,
        {
            "original_text": req.text,
            "user_prompt": f"请对以下文本进行去AI味润色，让文字更加自然：\n\n{req.text}",
        },
    )
    check_skill_error(result)
    processed = (result.get("json") or {}).get("processed_text", "") or result.get("content", "")
    return {"processed_text": processed}


# ============ 封面提示词 ============
@router.post("/{project_id}/cover/generate-prompt")
async def generate_cover_prompt(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """生成小说封面设计提示词（纯文本输出，不走 JSON 解析）"""
    proj = await get_user_project(db, project_id, user)
    ai_client = await AIClient.from_user_config(db, user.id)
    # 读取封面提示词模板
    import os
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "skills", "prompts", "novel_cover_prompt_template.md",
    )
    try:
        with open(template_path, encoding="utf-8") as f:
            template = f.read()
    except FileNotFoundError:
        template = (
            "你是专业的小说封面图像提示词设计专家。根据以下小说信息，直接输出中文图像生成提示词（纯提示词，无元叙述）。\n"
            "标题：{title}\n作者：{pen_name}\n类型：{genre}\n世界观：{world_desc}\n简介：{description}\n"
            "{pen_name_line}\n"
        )

    # 构建世界观描述
    world_parts = []
    if proj.world_atmosphere:
        world_parts.append(f"氛围基调：{proj.world_atmosphere}")
    if proj.world_time_period:
        world_parts.append(f"时代背景：{proj.world_time_period}")
    if proj.world_location:
        world_parts.append(f"地理设定：{proj.world_location}")
    world_desc = "。".join(world_parts) + "。" if world_parts else ""

    pen_name = (proj.pen_name or "").strip()
    pen_name_line = (
        f"作者名「{pen_name}」需以小号字体自然置于标题下方，与标题风格统一，不抢标题视觉权重。"
        if pen_name
        else "封面中除标题外，不得出现任何其他文字，包括作者名、副标题、英文、数字、Logo、品牌、水印、二维码、UI 元素、按钮、样机展示或任何无关文字。"
    )

    prompt_text = template.format(
        title=proj.title,
        pen_name=pen_name or "未设定",
        pen_name_line=pen_name_line,
        genre=proj.genre or "网文",
        narrative_pov=proj.narrative_pov or "第三人称",
        world_desc=world_desc + " " if world_desc else "",
        description=proj.synopsis or "暂无简介",
    )
    result = await ai_client.chat(
        messages=[{"role": "user", "content": prompt_text}],
        model=None,
        temperature=0.7,
        max_tokens=1200,
    )
    cover_prompt = result.get("content", "").strip()
    if not cover_prompt:
        raise HTTPException(500, "AI 未返回有效内容")
    # 保存到项目
    proj.cover_prompt = cover_prompt
    await db.commit()
    return {"cover_prompt": cover_prompt}


@router.post("/{project_id}/cover/generate-image")
async def generate_cover_image(
    project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """真实出图：调用图像生成 API 生成封面图片并保存到项目。

    复用用户配置的 base_url + api_key，调用 /v1/images/generations（OpenAI 兼容）。
    req: { prompt: 提示词, size?: "1024x1024", model?: "dall-e-3" }
    """
    import base64
    import os

    import httpx

    proj = await get_user_project(db, project_id, user)
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "请提供封面提示词")

    # 读取独立的图像生成 API 配置（用户必须在 AI 设置中配置）
    from sqlalchemy import select as sa_select

    from app.models.ai_model import AIModelConfig

    models = (
        await db.execute(sa_select(AIModelConfig).where(AIModelConfig.user_id == user.id))
    ).scalars().all()
    img_cfg = next((m for m in models if m.is_default), None) or (models[0] if models else None)
    if not img_cfg or not img_cfg.image_base_url or not img_cfg.image_api_key or not img_cfg.image_model:
        raise HTTPException(
            400,
            "未配置图像生成 API。请在「AI 设置」中填写图像生成的 Base URL、API Key 和模型名称后重试。"
            "你也可以复制上方提示词到 Midjourney/DALL-E 等工具手动生成。"
        )

    image_url = img_cfg.image_base_url.rstrip("/") + "/images/generations"
    headers = {"Authorization": f"Bearer {img_cfg.image_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": img_cfg.image_model,
        "prompt": prompt,
        "n": 1,
        "size": req.get("size", "1024x1024"),
        "response_format": "b64_json",
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(image_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise HTTPException(500, f"出图 API 返回 {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
    except httpx.RequestError as e:
        raise HTTPException(500, f"出图请求失败：{e}") from e

    # 保存图片到本地
    images = data.get("data", [])
    if not images:
        raise HTTPException(500, "出图 API 未返回图片")
    b64 = images[0].get("b64_json") or ""
    if not b64:
        # 部分 API 返回 url 而非 b64
        img_url = images[0].get("url", "")
        if img_url:
            proj.cover_url = img_url
            proj.cover_prompt = prompt
            await db.commit()
            return {"cover_url": img_url, "cover_prompt": prompt}
        raise HTTPException(500, "出图 API 未返回有效图片数据")

    cover_dir = "data/covers"
    os.makedirs(cover_dir, exist_ok=True)
    filename = f"{cover_dir}/project_{project_id}.png"
    with open(filename, "wb") as f:
        f.write(base64.b64decode(b64))
    proj.cover_url = f"/{filename}"
    proj.cover_prompt = prompt
    await db.commit()
    return {"cover_url": proj.cover_url, "cover_prompt": prompt}


# ============ 拆书导入反向解析 ============
@router.post("/book-import/reverse-suggest")
async def book_import_reverse_suggest(
    req: BookImportSuggestRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从小说文本反向提取项目信息"""
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "book_import_reverse_project_suggestion",
        ai_client,
        {
            "title": req.title or "未知书名",
            "sampled_text": req.sampled_text,
            "user_prompt": f"请从以下小说文本中提取项目信息（书名：{req.title}）。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/book-import/reverse-outlines")
async def book_import_reverse_outlines(
    req: BookImportOutlinesRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """从章节文本反向生成大纲并存库"""
    proj = await get_user_project(db, req.project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "book_import_reverse_outlines",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "start_chapter": str(req.start_chapter),
            "end_chapter": str(req.end_chapter),
            "expected_count": str(req.end_chapter - req.start_chapter + 1),
            "chapters_text": req.chapters_text,
            "user_prompt": f"请从以下章节文本中反向生成第{req.start_chapter}到{req.end_chapter}章的大纲。",
        },
    )
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    for item in outlines_data:
        db.add(
            Outline(
                project_id=req.project_id,
                chapter_number=item.get("chapter_number", 0),
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                key_points=item.get("key_points", []),
                emotion=item.get("emotion", ""),
                goal=item.get("goal", ""),
                structure=item,
            )
        )
        created.append(item)
    await db.commit()
    return {"outlines": created, "count": len(created)}


# ============ #23 拆书导入增强：TXT 解析 + 完整导入 ============
@router.post("/book-import/parse-txt")
async def parse_txt(
    req: dict,
    user=Depends(get_current_user),
):
    """解析 TXT 文本（base64 或纯文本），返回章节切分结果。

    req: { text?: str, base64?: str }
    """
    import base64

    from app.services.txt_parser_service import parse_txt_file

    raw = None
    if req.get("base64"):
        try:
            raw = base64.b64decode(req["base64"])
        except Exception:
            raise HTTPException(400, "base64 解码失败") from None
    elif req.get("text"):
        raw = req["text"].encode("utf-8")
    else:
        raise HTTPException(400, "请提供 text 或 base64")

    result = parse_txt_file(raw)
    # 不返回完整 text（可能很大），只返回章节和统计
    return {
        "chapters": result["chapters"][:200],  # 上限 200 章
        "stats": result["stats"],
    }


class FullImportReq(BaseModel):
    title: str
    genre: str = ""
    synopsis: str = ""
    chapters: list[dict] = []  # [{title, content, chapter_number}]


@router.post("/book-import/full-import")
async def full_import(
    req: FullImportReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """完整拆书导入：创建项目 + 批量导入章节（不走 AI 反向解析，直接落库）。

    用于：用户已有 TXT，想直接导入为项目（章节+大纲占位）。
    """
    new_proj = Project(
        user_id=user.id,
        title=req.title,
        genre=req.genre,
        synopsis=req.synopsis,
        chapter_count=len(req.chapters),
        current_word_count=sum(len(c.get("content", "")) for c in req.chapters),
        status="writing",
    )
    db.add(new_proj)
    await db.commit()
    await db.refresh(new_proj)

    created = 0
    total_words = 0
    for idx, ch in enumerate(req.chapters):
        title = ch.get("title", f"第{idx + 1}章")
        content = ch.get("content", "")
        word_count = len(content)
        total_words += word_count
        # 同步创建大纲占位
        outline = Outline(
            project_id=new_proj.id,
            chapter_number=idx + 1,
            title=title,
            summary=(content[:100] + "…") if content else "",
        )
        db.add(outline)
        await db.flush()
        chapter = Chapter(
            project_id=new_proj.id,
            outline_id=outline.id,
            chapter_number=idx + 1,
            title=title,
            content=content,
            summary=(content[:200] + "…") if len(content) > 200 else content,
            word_count=word_count,
            status="completed",
        )
        db.add(chapter)
        created += 1

    new_proj.current_word_count = total_words
    await db.commit()
    return {
        "project_id": new_proj.id,
        "title": new_proj.title,
        "chapter_count": created,
        "total_words": total_words,
    }


# ============ 拆书导入（持久化 + 一键拆解） ============
# 流程：上传 TXT → 解析并存库 → 一键拆解（采样立项 + 建项目 + 拆前N章大纲）
def _sample_chapters_text(chapters: list[dict], side: str, count: int) -> str:
    """从已切分章节中采样正文：side=head 取前 count 章，side=tail 取后 count 章。

    返回拼接后的纯文本（带章节标题），用于喂给 AI。
    """
    if not chapters:
        return ""
    if side == "tail":
        picked = chapters[-count:] if count < len(chapters) else chapters[:]
    else:
        picked = chapters[:count] if count < len(chapters) else chapters[:]
    parts = []
    for c in picked:
        title = c.get("title") or f"第{c.get('chapter_number', 0)}章"
        parts.append(f"{title}\n{c.get('content', '')}")
    return "\n\n".join(parts)


def _sample_chapters_evenly(chapters: list[dict], total_count: int = 12) -> str:
    """均匀采样：从前/中/后三段各取若干章，拼接成正文，用于设定提取。

    长篇只看开头会漏掉后文才出现的角色/势力/设定。本函数把 total_count 章
    均匀分布到全书（前段、中段、后段），保证覆盖全书关键节点。
    章数不足 total_count 时取全部。每章正文截断到 1500 字防 token 爆炸。
    """
    if not chapters:
        return ""
    n = len(chapters)
    if n <= total_count:
        picked = chapters[:]
    else:
        # 在 [0, n) 范围内均匀取 total_count 个点
        picked = [chapters[int(i * (n - 1) / (total_count - 1))] for i in range(total_count)]
    parts = []
    for c in picked:
        title = c.get("title") or f"第{c.get('chapter_number', 0)}章"
        content = (c.get("content", "") or "")[:1500]
        parts.append(f"{title}\n{content}")
    return "\n\n".join(parts)


async def _cascade_delete_project(task_db, project_id: int):
    """级联删除项目的所有关联数据（重新拆解时清理旧项目用）。

    比 crud.delete_project 更全：含 Item/Location/OrganizationMember 等拆书生成的表。
    """
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

    # 按 FK 依赖顺序删除（先删子表，最后删项目本身）
    for Model in [
        OrganizationMember,
        CharacterCareer,
        CharacterRelation,
        Item,
        Location,
        Organization,
        Career,
        Foreshadow,
        PlotAnalysis,
        StoryMemory,
        Outline,
        Character,
        WorldSetting,
        Chapter,
    ]:
        if not hasattr(Model, "project_id"):
            continue
        items = (
            (await task_db.execute(select(Model).where(Model.project_id == project_id)))
            .scalars()
            .all()
        )
        for it in items:
            await task_db.delete(it)

    # 最后删项目本身
    p = (
        await task_db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one_or_none()
    if p:
        await task_db.delete(p)


def _build_world_info_for_proj(proj) -> str:
    """构建项目世界观上下文（四维度），供自查 agent 使用。"""
    parts = []
    if proj.world_time_period:
        parts.append(f"时间背景：{proj.world_time_period}")
    if proj.world_location:
        parts.append(f"地理位置：{proj.world_location}")
    if proj.world_atmosphere:
        parts.append(f"氛围基调：{proj.world_atmosphere}")
    if proj.world_rules:
        parts.append(f"世界规则：{proj.world_rules}")
    return "\n".join(parts) if parts else "暂无世界观信息"


async def _cleanup_character_references(task_db, project_id: int, char_id: int):
    """删除角色前清理所有引用，防止悬空外键。

    清理范围：CharacterRelation（两端）、OrganizationMember、Character.organization_id、
    Item.owner_character_id。Location.resident_character_ids（JSON）只做尽力清理。
    """
    from sqlalchemy import func

    from app.models.character import Character, CharacterRelation
    from app.models.item import Item
    from app.models.organization_member import OrganizationMember

    # 1. 删除涉及该角色的关系（无论 from 还是 to）
    rels = (
        (
            await task_db.execute(
                select(CharacterRelation).where(
                    CharacterRelation.project_id == project_id,
                    (CharacterRelation.from_character_id == char_id)
                    | (CharacterRelation.to_character_id == char_id),
                )
            )
        )
        .scalars()
        .all()
    )
    for r in rels:
        await task_db.delete(r)

    # 2. 删除组织成员关系
    members = (
        (
            await task_db.execute(
                select(OrganizationMember).where(OrganizationMember.character_id == char_id)
            )
        )
        .scalars()
        .all()
    )
    for m in members:
        await task_db.delete(m)

    # 3. 物品持有者置空
    items = (
        (
            await task_db.execute(
                select(Item).where(Item.owner_character_id == char_id)
            )
        )
        .scalars()
        .all()
    )
    for it in items:
        it.owner_character_id = None

    # 4. 同项目其他角色的 organization_id 若指向被删角色所在组织——这里不动组织，
    #    只清 Character 自身（被删角色的 organization_id 随角色一起删除，无需单独清）


async def _cleanup_organization_references(task_db, project_id: int, org_id: int):
    """删除组织前清理引用：Character.organization_id、OrganizationMember。"""
    from app.models.character import Character
    from app.models.organization_member import OrganizationMember

    # 角色的 organization_id 置空
    chars = (
        (
            await task_db.execute(
                select(Character).where(
                    Character.project_id == project_id, Character.organization_id == org_id
                )
            )
        )
        .scalars()
        .all()
    )
    for c in chars:
        c.organization_id = None

    members = (
        (
            await task_db.execute(
                select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    for m in members:
        await task_db.delete(m)


async def _apply_consistency_fixes(task_db, project_id: int, check_json: dict) -> int:
    """应用一致性自查给出的修复指令，返回已修复数量。

    支持的 action：
    - clear_career / set_career：修正角色 main_career_stage_desc
    - update_field：修改实体某个字段（target_type + target_name 定位，new_value 填新值）
    - remove_relation：删除两端无效的角色关系
    - delete_entity：删除错误实体（角色/组织/地点/物品），含引用清理防悬空
    - merge_entity：合并重复实体（target_name=被删的重复项，new_value=保留的标准项名）
    - note_only：仅记录不自动改
    """
    if not isinstance(check_json, dict):
        return 0
    issues = check_json.get("issues") or []
    if not isinstance(issues, list) or not issues:
        return 0

    from app.models.character import Character, CharacterRelation
    from app.models.item import Item
    from app.models.location import Location
    from app.models.organization import Organization

    fixed = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        fix = issue.get("fix") or {}
        if not isinstance(fix, dict):
            continue
        action = fix.get("action")
        target_type = str(fix.get("target_type", "")).strip().lower()
        target_name = str(fix.get("target_name", "")).strip()
        new_value = str(fix.get("new_value", ""))

        # ===== 角色职业修正 =====
        if action in ("clear_career", "set_career") and target_name:
            char = (
                await task_db.execute(
                    select(Character).where(
                        Character.project_id == project_id, Character.name == target_name
                    )
                )
            ).scalar_one_or_none()
            if char:
                char.main_career_stage_desc = new_value[:200]
                fixed += 1

        # ===== 通用字段修改（修正与世界观冲突的身份/描述等）=====
        elif action == "update_field" and target_type and target_name:
            # target_name 格式约定："实体名.字段名"（AI 在 description 里说明），或直接字段名
            # 简化：只支持角色 identity 字段修正（最常见的世界观冲突场景）
            if target_type == "character":
                char = (
                    await task_db.execute(
                        select(Character).where(
                            Character.project_id == project_id, Character.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if char:
                    # new_value 用 "字段=值" 格式指定要改的字段，缺省改 identity
                    field, _, val = new_value.partition("=")
                    field = field.strip() or "identity"
                    val = (val if val else new_value).strip()
                    if hasattr(char, field) and field not in ("id", "project_id", "name"):
                        setattr(char, field, val[:2000])
                        fixed += 1
            elif target_type == "organization":
                org = (
                    await task_db.execute(
                        select(Organization).where(
                            Organization.project_id == project_id, Organization.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if org:
                    field, _, val = new_value.partition("=")
                    field = field.strip() or "description"
                    val = (val if val else new_value).strip()
                    if hasattr(org, field) and field not in ("id", "project_id", "name"):
                        setattr(org, field, val[:2000])
                        fixed += 1

        # ===== 删除无效关系 =====
        elif action == "remove_relation" and target_name:
            rels = (
                await task_db.execute(
                    select(CharacterRelation).where(
                        CharacterRelation.project_id == project_id
                    )
                )
            ).scalars().all()
            for r in rels:
                if target_name in (r.description or ""):
                    await task_db.delete(r)
                    fixed += 1

        # ===== 删除错误实体（含引用清理）=====
        elif action == "delete_entity" and target_type and target_name:
            if target_type == "character":
                char = (
                    await task_db.execute(
                        select(Character).where(
                            Character.project_id == project_id, Character.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if char:
                    await _cleanup_character_references(task_db, project_id, char.id)
                    await task_db.delete(char)
                    fixed += 1
            elif target_type == "organization":
                org = (
                    await task_db.execute(
                        select(Organization).where(
                            Organization.project_id == project_id, Organization.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if org:
                    await _cleanup_organization_references(task_db, project_id, org.id)
                    await task_db.delete(org)
                    fixed += 1
            elif target_type == "location":
                loc = (
                    await task_db.execute(
                        select(Location).where(
                            Location.project_id == project_id, Location.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if loc:
                    await task_db.delete(loc)
                    fixed += 1
            elif target_type == "item":
                it = (
                    await task_db.execute(
                        select(Item).where(
                            Item.project_id == project_id, Item.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if it:
                    await task_db.delete(it)
                    fixed += 1

        # ===== 合并重复实体（删除重复项，保留标准项）=====
        elif action == "merge_entity" and target_type and target_name and new_value:
            # target_name=被删的重复项，new_value=保留的标准项名
            if target_type == "character":
                dup = (
                    await task_db.execute(
                        select(Character).where(
                            Character.project_id == project_id, Character.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    await _cleanup_character_references(task_db, project_id, dup.id)
                    await task_db.delete(dup)
                    fixed += 1
            elif target_type == "organization":
                dup = (
                    await task_db.execute(
                        select(Organization).where(
                            Organization.project_id == project_id, Organization.name == target_name
                        )
                    )
                ).scalar_one_or_none()
                if dup:
                    await _cleanup_organization_references(task_db, project_id, dup.id)
                    await task_db.delete(dup)
                    fixed += 1

    if fixed:
        await task_db.commit()
    return fixed


@router.post("/book-import/upload")
async def book_import_upload(
    req: BookImportUploadRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """上传 TXT 并解析入库。

    req: { filename?, title?, text?, base64? }（text / base64 二选一）
    返回书籍摘要信息（不含正文）。
    """
    import base64 as _b64
    import os

    from app.models.imported_book import ImportedBook
    from app.services.txt_parser_service import parse_txt_file

    raw: bytes | None = None
    if req.base64:
        try:
            raw = _b64.b64decode(req.base64)
        except Exception:
            raise HTTPException(400, "base64 解码失败") from None
    elif req.text:
        raw = req.text.encode("utf-8")
    else:
        raise HTTPException(400, "请提供 text 或 base64")

    parsed = parse_txt_file(raw)
    chapters = parsed.get("chapters", [])
    stats = parsed.get("stats", {})

    # 推断书名：显式传入 > 文件名（去扩展名）> 兜底
    title = (req.title or "").strip()
    if not title:
        fn = (req.filename or "").strip()
        if fn:
            title = os.path.splitext(fn)[0]
    if not title:
        title = "导入小说"

    book = ImportedBook(
        user_id=user.id,
        title=title,
        source_filename=(req.filename or "")[:300],
        total_chapters=len(chapters),
        total_chars=stats.get("total_chars", 0),
        raw_text=parsed.get("text", ""),
        has_strong_titles=1 if stats.get("has_strong_titles") else 0,
        status="imported",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book.to_dict()


@router.get("/book-import/{book_id}")
async def book_import_detail(
    book_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """书籍详情 + 前 10 章预览（标题/字数，不含正文）。"""
    from app.models.imported_book import ImportedBook
    from app.services.txt_parser_service import parse_txt_file

    result = await db.execute(
        select(ImportedBook).where(ImportedBook.id == book_id, ImportedBook.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, "书籍不存在或无权访问")

    # 按需切分一次取预览（不存章节，临时切）
    preview = []
    if book.raw_text:
        parsed = parse_txt_file(book.raw_text.encode("utf-8"))
        for c in parsed.get("chapters", [])[:10]:
            preview.append(
                {
                    "chapter_number": c.get("chapter_number", 0),
                    "title": c.get("title", ""),
                    "word_count": len(c.get("content", "")),
                }
            )
    info = book.to_dict()
    info["preview"] = preview
    return info


@router.delete("/book-import/{book_id}")
async def book_import_delete(
    book_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """删除导入书籍记录。"""
    from app.models.imported_book import ImportedBook

    result = await db.execute(
        select(ImportedBook).where(ImportedBook.id == book_id, ImportedBook.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, "书籍不存在或无权访问")
    await db.delete(book)
    await db.commit()
    return {"ok": True}


@router.post("/book-import/{book_id}/deconstruct")
async def book_import_deconstruct(
    book_id: int,
    req: BookImportDeconstructRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """异步一键拆解：立即返回 task_id，后台执行采样立项→建项目→拆大纲。

    req: { sample_side: head|tail, sample_count=5, outline_chapters=20 }
    前端通过右下角浮窗查看进度。
    """
    from app.models.imported_book import ImportedBook

    # 校验书籍存在
    result = await db.execute(
        select(ImportedBook).where(ImportedBook.id == book_id, ImportedBook.user_id == user.id)
    )
    book = result.scalar_one_or_none()
    if not book:
        raise HTTPException(404, "书籍不存在或无权访问")
    if not book.raw_text:
        raise HTTPException(400, "书籍正文为空，无法拆解")

    from app.services.async_ai_service import submit_async_task

    outline_chapters = max(5, req.outline_chapters or 20)

    async def _run_deconstruct(task_id: int, payload: dict):
        import logging

        from app.services import background_task_service as bgs
        from app.services.txt_parser_service import parse_txt_file

        logger = logging.getLogger(__name__)
        tracker = bgs.TaskProgressTracker(task_id)

        async with async_session() as task_db:
            # 1. 取书
            bk = (
                await task_db.execute(
                    select(ImportedBook).where(
                        ImportedBook.id == payload["book_id"],
                        ImportedBook.user_id == payload["user_id"],
                    )
                )
            ).scalar_one_or_none()
            if not bk or not bk.raw_text:
                await tracker.fail("书籍不存在或正文为空")
                return

            # 重新拆解：若该书已生成过项目，先级联清理旧项目所有数据，避免残留
            if bk.created_project_id:
                await tracker.update(stage="preparing", message="清理上次拆解的旧项目...")
                try:
                    await _cascade_delete_project(task_db, bk.created_project_id)
                    await task_db.commit()
                    bk.created_project_id = None
                    bk.status = "uploaded"
                    logger.info("已清理旧项目 %s，准备重新拆解", bk.created_project_id)
                except Exception as e:
                    logger.warning("清理旧项目异常（继续重新拆解）：%s", e)

            await tracker.update(stage="preparing", message="解析章节...")
            chapters = parse_txt_file(bk.raw_text.encode("utf-8")).get("chapters", [])
            if not chapters:
                await tracker.fail("未识别到章节")
                return

            engine, ai_client = await make_engine_and_client(task_db, payload["user_id"])

            # 2. 立项采样
            await tracker.update(stage="analyzing", message="AI 分析项目信息...")
            sample_count = max(1, payload["sample_count"])
            sampled_text = _sample_chapters_text(chapters, payload["sample_side"], sample_count)
            sug_result = await engine.execute_skill(
                "book_import_reverse_project_suggestion",
                ai_client,
                {
                    "title": bk.title or "未知书名",
                    "sampled_text": sampled_text,
                    "user_prompt": f"请从以下小说文本中提取项目信息（书名：{bk.title}）。",
                },
            )
            if sug_result.get("error"):
                await tracker.fail(f"项目分析失败: {sug_result['error']}")
                return
            project_info = sug_result.get("json") or {}

            # 3. 建项目
            genre = project_info.get("genre") or ""
            synopsis = project_info.get("description") or project_info.get("synopsis") or ""
            new_proj = Project(
                user_id=payload["user_id"],
                title=project_info.get("title") or bk.title,
                genre=genre,
                synopsis=synopsis,
                chapter_count=payload["outline_chapters"],
                current_word_count=0,
                target_word_count=project_info.get("target_words") or 0,
                narrative_pov=project_info.get("narrative_perspective") or "第三人称",
                status="active",
            )
            task_db.add(new_proj)
            await task_db.commit()
            await task_db.refresh(new_proj)

            # 4. 提取角色档案（均匀采样全书，避免只看开头漏掉后文出场的角色）
            #    先于大纲生成，让大纲能复用已提取的角色名，避免大纲与角色各编一套名字
            #    导致 validate_outline 补建第二套角色（总数膨胀）。
            await tracker.update(stage="generating", message="提取角色档案...", progress=20)
            from app.models.character import Character
            try:
                char_sample = _sample_chapters_evenly(chapters, 12)
                char_result = await engine.execute_skill(
                    "book_import_reverse_characters",
                    ai_client,
                    {
                        "title": new_proj.title,
                        "genre": genre or "网文",
                        "synopsis": synopsis or "",
                        "chapters_text": char_sample,
                        "user_prompt": "请从以下正文中提取角色档案。",
                    },
                )
                if char_result.get("error"):
                    logger.warning("拆书角色提取失败：%s", char_result["error"])
                else:
                    char_data = char_result.get("json") or []
                    if isinstance(char_data, dict):
                        char_data = char_data.get("characters") or char_data.get("data") or []
                    # 复用 init 的 _save_characters 统一保存，确保字段与正常 init 角色完全一致
                    # （含多别名兜底、职业匹配、growth_experience/story_goal/weakness/arc_type 等完整字段）
                    from app.api.routes.project_init import _save_characters

                    MAX_CORE_CHARS = 8  # 只保留核心角色，边缘角色不入库（避免冗余）
                    truncated = char_data[:MAX_CORE_CHARS]
                    saved_names = set()
                    await _save_characters(task_db, new_proj.id, truncated, saved_names)
                    await task_db.commit()
                    logger.info("拆书角色提取完成：新增 %d 个角色（复用 _save_characters）", len(saved_names))
            except Exception as e:
                logger.warning("拆书角色提取异常：%s", e)

            # 收集已提取的角色名，供大纲生成复用（避免大纲另编一套角色名）
            existing_char_list = (
                (await task_db.execute(
                    select(Character.name, Character.role).where(Character.project_id == new_proj.id)
                )).all()
            )
            char_names_hint = "、".join(
                f"{n}（{r or '角色'}）" for n, r in existing_char_list[:12]
            ) if existing_char_list else ""

            # 5. 拆大纲（按 5 章/批）
            available = min(payload["outline_chapters"], len(chapters))
            theme = project_info.get("theme") or ""
            narrative_pov = project_info.get("narrative_perspective") or "第三人称"
            batch_size = 5
            total_batches = (available + batch_size - 1) // batch_size
            created_outlines = 0
            batches_done = 0
            # 累积前序批次已生成的大纲摘要，让后续批次感知前情，保持剧情/角色连贯
            prior_outlines_summary = ""

            for start_no in range(1, available + 1, batch_size):
                # 检查取消
                bk2 = (
                    await task_db.execute(
                        select(ImportedBook).where(ImportedBook.id == payload["book_id"])
                    )
                ).scalar_one_or_none()
                batch_idx = (start_no - 1) // batch_size
                await tracker.update(
                    stage="generating",
                    message=f"拆解大纲 第{start_no}-{min(start_no + batch_size - 1, available)}章（批次 {batch_idx + 1}/{total_batches}）",
                    progress=int(batch_idx / total_batches * 100),
                )

                end_no = min(start_no + batch_size - 1, available)
                batch_chapters = chapters[start_no - 1 : end_no]
                batch_text = _sample_chapters_text(batch_chapters, "head", len(batch_chapters))
                if not batch_text.strip():
                    continue
                # 拼入前情提要（前序批次已生成的大纲），让本批保持连贯
                if prior_outlines_summary:
                    prior_block = (
                        f"【前情提要——前序章节已生成的大纲，请保持剧情/角色/伏笔连贯，不要断裂或重复】\n"
                        f"{prior_outlines_summary}\n\n"
                    )
                    continuity_hint = "本批接续前情，保持叙事连贯。"
                else:
                    prior_block = ""
                    continuity_hint = ""
                # 角色名约束：强制大纲复用已提取的角色名，不得另编新名（避免角色库与大纲各一套）
                char_constraint = (
                    f"【角色名约束】大纲 characters 字段必须只使用以下已建立的角色名：{char_names_hint}。"
                    f"不得自创新角色名；如需新角色，先用已有配角承担。"
                    if char_names_hint
                    else ""
                )
                try:
                    o_result = await engine.execute_skill(
                        "book_import_reverse_outlines",
                        ai_client,
                        {
                            "title": new_proj.title,
                            "genre": genre or "网文",
                            "theme": theme,
                            "narrative_perspective": narrative_pov,
                            "start_chapter": str(start_no),
                            "end_chapter": str(end_no),
                            "expected_count": str(end_no - start_no + 1),
                            "chapters_text": batch_text,
                            "user_prompt": (
                                f"{prior_block}"
                                f"{char_constraint}"
                                f"请从以下章节文本中反向生成第{start_no}到{end_no}章的大纲。"
                                f"{continuity_hint}"
                            ),
                        },
                    )
                    if o_result.get("error"):
                        logger.warning("拆书大纲批次 %s-%s 失败：%s", start_no, end_no, o_result["error"])
                        continue
                    outlines_data = o_result.get("json") or []
                    if not isinstance(outlines_data, list):
                        continue
                    # 复用 _build_outline 统一构建，确保 characters/scenes 等字段格式
                    # 与正常 init 大纲一致（清洗角色/组织、过滤空场景、规范章号）
                    from app.api.routes.projects_pkg.outlines import _build_outline

                    # 收集已建角色名/组织名，传给 _build_outline 做角色/组织区分校正
                    from app.models.organization import Organization

                    char_name_set = {
                        n for n in (
                            await task_db.execute(
                                select(Character.name).where(Character.project_id == new_proj.id)
                            )
                        ).scalars()
                    }
                    org_name_set = {
                        n for n in (
                            await task_db.execute(
                                select(Organization.name).where(
                                    Organization.project_id == new_proj.id
                                )
                            )
                        ).scalars()
                    }

                    batch_summary_parts = []
                    created_outline_objs = []
                    for idx, item in enumerate(outlines_data):
                        if not isinstance(item, dict):
                            continue
                        o = _build_outline(
                            new_proj.id, item, offset=0, index=idx,
                            char_names=char_name_set, org_names=org_name_set,
                        )
                        # chapter_number 以 AI 返回为准，兜底用批次起始章号
                        ch_num = item.get("chapter_number")
                        if not isinstance(ch_num, int) or ch_num < 1:
                            ch_num = start_no + idx
                        o.chapter_number = ch_num
                        task_db.add(o)
                        created_outline_objs.append(o)
                        created_outlines += 1
                        # 累积本批大纲的精简摘要（章号+标题+summary前80字），供下一批参考
                        ch_title = str(item.get("title", ""))[:30]
                        ch_summary = str(item.get("summary", ""))[:80]
                        batch_summary_parts.append(f"第{ch_num}章《{ch_title}》：{ch_summary}")

                    # flush 让大纲对象拿到 id，供后续章节引用
                    if created_outline_objs:
                        await task_db.flush()
                        # 与正常 init 一致：1对1模式自动为每条大纲创建对应空章节
                        from app.models.chapter import Chapter

                        for o in created_outline_objs:
                            existing_ch = (
                                (
                                    await task_db.execute(
                                        select(Chapter).where(
                                            Chapter.project_id == new_proj.id,
                                            Chapter.chapter_number == o.chapter_number,
                                        )
                                    )
                                )
                                .scalars()
                                .first()
                            )
                            if existing_ch:
                                continue
                            ch = Chapter(
                                project_id=new_proj.id,
                                chapter_number=o.chapter_number,
                                title=o.title,
                                summary=o.summary[:200] if o.summary else "",
                                status="draft",
                                sub_index=1,
                                generation_mode="one_to_one",
                            )
                            task_db.add(ch)
                    # 更新前情摘要（控制总长度，避免 token 爆炸——最多保留最近 10 章摘要）
                    if batch_summary_parts:
                        prior_outlines_summary = "\n".join(batch_summary_parts)
                        # 若累积过长，只保留最近的若干章
                        lines = prior_outlines_summary.split("\n")
                        if len(lines) > 10:
                            prior_outlines_summary = "（更早章节略）\n" + "\n".join(lines[-10:])
                    batches_done += 1
                    await task_db.commit()
                except Exception as e:
                    logger.warning("拆书大纲批次 %s-%s 异常：%s", start_no, end_no, e)
                    continue

            # 5. 提取世界观设定（均匀采样全书，覆盖中后期才展开的世界观）
            await tracker.update(stage="generating", message="提取世界观设定...", progress=80)
            try:
                world_sample = _sample_chapters_evenly(chapters, 12)
                world_result = await engine.execute_skill(
                    "book_import_reverse_world",
                    ai_client,
                    {
                        "title": new_proj.title,
                        "genre": genre or "网文",
                        "synopsis": synopsis or "",
                        "chapters_text": world_sample,
                        "user_prompt": "请从以下正文中提取世界观设定。",
                    },
                )
                if world_result.get("error"):
                    logger.warning("拆书世界观提取失败：%s", world_result["error"])
                else:
                    wd = world_result.get("json") or {}
                    if isinstance(wd, dict):
                        if wd.get("world_time_period"):
                            new_proj.world_time_period = wd["world_time_period"][:500]
                        if wd.get("world_location"):
                            new_proj.world_location = wd["world_location"][:500]
                        if wd.get("world_atmosphere"):
                            new_proj.world_atmosphere = wd["world_atmosphere"][:500]
                        if wd.get("world_rules"):
                            new_proj.world_rules = wd["world_rules"][:1000]
                        await task_db.commit()
                        logger.info("拆书世界观提取完成")
            except Exception as e:
                logger.warning("拆书世界观提取异常：%s", e)

            # 7. 补齐设定：复用项目初始化步骤，补全拆书未覆盖的模块。
            # 拆书已完成「角色 / 大纲 / 核心世界观」，这里补：
            # 详细世界设定 → 职业体系 → 地点 → 物品 → 组织势力 → 角色关系 → 大纲验证补全。
            # 补生成以已拆出的 proj/角色/世界观为上下文（init 步骤 prompt 用 _build_world_info + 查库角色）。
            from types import SimpleNamespace

            from app.api.routes.project_init import (
                _generate_world_details,
                _step_career,
                _step_items,
                _step_locations,
                _step_org,
                _step_relations,
                _step_validate_outline,
            )

            # init 步骤签名是 (db, task, pid, proj, engine, ai_client)，会写 task 的 *_done/progress/status_message 并 commit。
            # 拆书用的是 BackgroundTask，没有这些字段；用 SimpleNamespace 提供 duck-type 兼容对象，
            # 它不是 ORM 映射对象，commit 不会把它持久化，无副作用。
            mock_task = SimpleNamespace(
                progress=0,
                status_message="",
                world_done=0,
                career_done=0,
                org_done=0,
                characters_done=0,
                assign_careers_done=0,
                relations_done=0,
                assign_org_members_done=0,
                locations_done=0,
                items_done=0,
                outline_done=0,
                validate_done=0,
            )

            # 均匀采样全书正文，只喂给「最依赖原书细节」的步骤（组织、角色关系），
            # 减少与原书的气质断层。其余步骤（详细设定/职业/地点/物品）的题材已被
            # 核心世界观四字段 + 已拆角色锁死，喂正文边际收益低却浪费 token，故不喂。
            _source_text = _sample_chapters_evenly(chapters, 8)

            # 各补齐步骤的 (label, 可调用)。单步失败仅告警并继续，不影响已生成内容。
            async def _run_fill_step(label, coro_factory):
                await tracker.update(stage="generating", message=label)
                try:
                    await coro_factory()
                except Exception as e:
                    logger.warning("拆书补齐[%s]异常：%s", label, e)

            # 详细设定/职业/地点/物品：不喂正文（题材已被已拆结果锁定，省 token）
            await _run_fill_step(
                "生成详细世界设定...",
                lambda: _generate_world_details(task_db, new_proj.id, new_proj, engine, ai_client),
            )
            await _run_fill_step(
                "生成职业体系...",
                lambda: _step_career(task_db, mock_task, new_proj.id, new_proj, engine, ai_client),
            )
            await _run_fill_step(
                "生成地点地图...",
                lambda: _step_locations(task_db, mock_task, new_proj.id, new_proj, engine, ai_client),
            )
            await _run_fill_step(
                "生成物品道具...",
                lambda: _step_items(task_db, mock_task, new_proj.id, new_proj, engine, ai_client),
            )
            # 组织/关系：最依赖原书人际与势力细节，喂入正文采样，让 AI 据此改编
            await _run_fill_step(
                "生成组织势力...",
                lambda: _step_org(
                    task_db, mock_task, new_proj.id, new_proj, engine, ai_client,
                    source_text=_source_text,
                ),
            )
            await _run_fill_step(
                "生成角色关系...",
                lambda: _step_relations(
                    task_db, mock_task, new_proj.id, new_proj, engine, ai_client,
                    source_text=_source_text,
                ),
            )
            await _run_fill_step(
                "验证并补全大纲...",
                lambda: _step_validate_outline(
                    task_db, mock_task, new_proj.id, new_proj, engine, ai_client
                ),
            )

            # 兜底：扫描所有没有对应章节的大纲，补建缺失的空章节（确保用户在章节页
            # 不会看到多余的"从大纲创建"按钮——拆书模式下章节应已全部自动建好）
            try:
                from app.models.chapter import Chapter

                all_outlines = (
                    await task_db.execute(
                        select(Outline).where(Outline.project_id == new_proj.id)
                    )
                ).scalars().all()
                existing_ch_nums = set(
                    (
                        await task_db.execute(
                            select(Chapter.chapter_number).where(
                                Chapter.project_id == new_proj.id
                            )
                        )
                    ).scalars()
                )
                missing = [o for o in all_outlines if o.chapter_number not in existing_ch_nums]
                for o in missing:
                    task_db.add(
                        Chapter(
                            project_id=new_proj.id,
                            chapter_number=o.chapter_number,
                            title=o.title,
                            summary=o.summary[:200] if o.summary else "",
                            status="draft",
                            sub_index=1,
                            generation_mode="one_to_one",
                        )
                    )
                if missing:
                    await task_db.commit()
                    logger.info("拆书兜底补建 %d 个空章节", len(missing))
            except Exception as e:
                logger.warning("拆书兜底补建章节异常：%s", e)

            # 8. 一致性自查（轻量 agent）：用工具查实体，发现矛盾并自动修复
            await tracker.update(stage="generating", message="设定一致性自查...", progress=95)
            try:
                from app.services.chapter_tools import get_chapter_tools, make_tool_executor

                check_result = await engine.execute_skill(
                    "book_import_consistency_check",
                    ai_client,
                    {
                        "title": new_proj.title,
                        "genre": genre or "网文",
                        "synopsis": synopsis or "",
                        "world_info": _build_world_info_for_proj(new_proj),
                        "user_prompt": "请用工具自查项目设定一致性，找出矛盾并给出修复指令。",
                    },
                    tools=get_chapter_tools(),
                    tool_executor=make_tool_executor(task_db, new_proj.id),
                )
                if check_result.get("error"):
                    logger.warning("拆书一致性自查失败：%s", check_result["error"])
                else:
                    fixed = await _apply_consistency_fixes(
                        task_db, new_proj.id, check_result.get("json") or {}
                    )
                    if fixed:
                        logger.info("拆书一致性自查修复 %d 处", fixed)
                        await tracker.update(
                            stage="generating", message=f"一致性自查完成（自动修复 {fixed} 处）"
                        )
            except Exception as e:
                logger.warning("拆书一致性自查异常：%s", e)

            # 9. 回填
            bk.status = "project_created"
            bk.created_project_id = new_proj.id
            await task_db.commit()

            await tracker.complete(
                message=f"拆解完成：项目《{new_proj.title}》，{created_outlines} 条大纲 + 角色 + 世界观 + 详细设定/职业/地点/物品/组织/关系 + 一致性自查"
            )

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=None,
        task_type="book_import",
        title=f"拆书导入：{book.title}",
        payload={
            "book_id": book_id,
            "user_id": user.id,
            "sample_side": req.sample_side,
            "sample_count": req.sample_count,
            "outline_chapters": outline_chapters,
        },
        runner=_run_deconstruct,
    )
    return {"task_id": task_id}


# ============ MCP 增强 ============
@router.post("/{project_id}/mcp/test-tool")
async def mcp_test_tool(
    project_id: int,
    req: McpToolTestRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """MCP 工具测试"""
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    sys_skill = await engine.get_skill("mcp_tool_test_system")
    usr_skill = await engine.get_skill("mcp_tool_test")
    ctx = {
        "plugin_name": req.plugin_name,
        "tool_list": json.dumps(req.tool_list, ensure_ascii=False),
    }
    if sys_skill and usr_skill:
        sys_prompt = substitute_vars(sys_skill.system_prompt, ctx)
        usr_prompt = substitute_vars(usr_skill.system_prompt, ctx)
        result = await ai_client.chat_json_retry(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt},
            ]
        )
    else:
        result = await engine.execute_skill(
            "mcp_tool_test",
            ai_client,
            {
                "plugin_name": req.plugin_name,
                "user_prompt": f"请分析 MCP 插件 {req.plugin_name} 的可用工具并推荐测试方案。",
            },
        )
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/mcp/world-planning")
async def mcp_world_planning(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """MCP 世界观规划"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "mcp_world_building_planning",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "theme": "",
            "description": proj.synopsis or "暂无简介",
            "user_prompt": f"请为小说「{proj.title}」进行世界观研究，提供构建建议。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/mcp/character-planning")
async def mcp_character_planning(
    project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)
):
    """MCP 角色规划"""
    proj = await get_user_project(db, project_id, user)
    worlds = (
        (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id)))
        .scalars()
        .all()
    )
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill(
        "mcp_character_planning",
        ai_client,
        {
            "title": proj.title,
            "genre": proj.genre or "网文",
            "theme": "",
            "time_period": "",
            "location": "",
            "world_info": world_info,
            "user_prompt": f"请为小说「{proj.title}」进行角色研究，提供角色设计建议。",
        },
    )
    check_skill_error(result)
    return result.get("json") or {}
