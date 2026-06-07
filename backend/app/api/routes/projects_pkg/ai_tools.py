"""AI 工具：灵感激发 / 去味 / 封面提示词 / 拆书导入 / MCP"""
import json
from app.api.routes.projects_pkg.base import *


router = make_router()


# ============ 灵感激发（旧版单次） ============
@router.post("/{project_id}/inspire")
async def inspire(project_id: int, req: InspireRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("inspire", ai_client, {
        "idea": req.idea,
        "user_prompt": f"我的想法是：{req.idea}，请帮我拓展成创作方案。",
    })
    check_skill_error(result)
    return result.get("json") or {}


# ============ AI 去味/润色 ============
@router.post("/{project_id}/ai-denoising")
async def ai_denoising(project_id: int, req: AiDenoisingRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """让文本更自然，去除 AI 味"""
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("ai_denoising", ai_client, {
        "original_text": req.text,
        "user_prompt": f"请对以下文本进行去AI味润色，让文字更加自然：\n\n{req.text}",
    })
    check_skill_error(result)
    processed = (result.get("json") or {}).get("processed_text", "") or result.get("content", "")
    return {"processed_text": processed}


# ============ 封面提示词 ============
@router.post("/{project_id}/cover/generate-prompt")
async def generate_cover_prompt(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """生成小说封面设计提示词"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("novel_cover_prompt_template", ai_client, {
        "title": proj.title, "genre": proj.genre or "网文", "theme": "",
        "description": proj.synopsis or "暂无简介",
        "user_prompt": f"请为小说「{proj.title}」生成封面设计提示词。题材：{proj.genre}，简介：{proj.synopsis}",
    })
    check_skill_error(result)
    cover_prompt = result.get("content", "") or result.get("json") or ""
    return {"cover_prompt": cover_prompt}


@router.post("/{project_id}/cover/generate-image")
async def generate_cover_image(project_id: int, req: dict, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """真实出图：调用图像生成 API 生成封面图片并保存到项目。

    复用用户配置的 base_url + api_key，调用 /v1/images/generations（OpenAI 兼容）。
    req: { prompt: 提示词, size?: "1024x1024", model?: "dall-e-3" }
    """
    import httpx
    import base64
    import os

    proj = await get_user_project(db, project_id, user)
    prompt = req.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "请提供封面提示词")

    ai_client = await AIClient.from_user_config(db, user.id)
    image_url = (ai_client.base_url or "").rstrip("/") + "/images/generations"

    headers = {"Authorization": f"Bearer {ai_client.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": req.get("model", "dall-e-3"),
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
        raise HTTPException(500, f"出图请求失败：{e}")

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

    cover_dir = f"data/covers"
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
async def book_import_reverse_suggest(req: BookImportSuggestRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """从小说文本反向提取项目信息"""
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("book_import_reverse_project_suggestion", ai_client, {
        "title": req.title or "未知书名", "sampled_text": req.sampled_text,
        "user_prompt": f"请从以下小说文本中提取项目信息（书名：{req.title}）。",
    })
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/book-import/reverse-outlines")
async def book_import_reverse_outlines(req: BookImportOutlinesRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """从章节文本反向生成大纲并存库"""
    proj = await get_user_project(db, req.project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("book_import_reverse_outlines", ai_client, {
        "title": proj.title, "genre": proj.genre or "网文",
        "start_chapter": str(req.start_chapter), "end_chapter": str(req.end_chapter),
        "expected_count": str(req.end_chapter - req.start_chapter + 1),
        "chapters_text": req.chapters_text,
        "user_prompt": f"请从以下章节文本中反向生成第{req.start_chapter}到{req.end_chapter}章的大纲。",
    })
    check_skill_error(result)
    outlines_data = result.get("json") or []
    if not isinstance(outlines_data, list):
        raise HTTPException(500, "AI 返回的大纲格式不正确")
    created = []
    for item in outlines_data:
        db.add(Outline(
            project_id=req.project_id,
            chapter_number=item.get("chapter_number", 0),
            title=item.get("title", ""), summary=item.get("summary", ""),
            key_points=item.get("key_points", []), emotion=item.get("emotion", ""),
            goal=item.get("goal", ""), structure=item,
        ))
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
            raise HTTPException(400, "base64 解码失败")
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
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
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
        title = ch.get("title", f"第{idx+1}章")
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


# ============ MCP 增强 ============
@router.post("/{project_id}/mcp/test-tool")
async def mcp_test_tool(project_id: int, req: McpToolTestRequest, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """MCP 工具测试"""
    await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    sys_skill = await engine.get_skill("mcp_tool_test_system")
    usr_skill = await engine.get_skill("mcp_tool_test")
    ctx = {"plugin_name": req.plugin_name, "tool_list": json.dumps(req.tool_list, ensure_ascii=False)}
    if sys_skill and usr_skill:
        sys_prompt = substitute_vars(sys_skill.system_prompt, ctx)
        usr_prompt = substitute_vars(usr_skill.system_prompt, ctx)
        result = await ai_client.chat_json_retry(messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": usr_prompt}])
    else:
        result = await engine.execute_skill("mcp_tool_test", ai_client, {
            "plugin_name": req.plugin_name,
            "user_prompt": f"请分析 MCP 插件 {req.plugin_name} 的可用工具并推荐测试方案。",
        })
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/mcp/world-planning")
async def mcp_world_planning(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """MCP 世界观规划"""
    proj = await get_user_project(db, project_id, user)
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("mcp_world_building_planning", ai_client, {
        "title": proj.title, "genre": proj.genre or "网文", "theme": "",
        "description": proj.synopsis or "暂无简介",
        "user_prompt": f"请为小说「{proj.title}」进行世界观研究，提供构建建议。",
    })
    check_skill_error(result)
    return result.get("json") or {}


@router.post("/{project_id}/mcp/character-planning")
async def mcp_character_planning(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """MCP 角色规划"""
    proj = await get_user_project(db, project_id, user)
    worlds = (await db.execute(select(WorldSetting).where(WorldSetting.project_id == project_id))).scalars().all()
    world_info = "\n".join([f"- {w.name}: {w.content[:200]}" for w in worlds]) or "暂无"
    engine, ai_client = await make_engine_and_client(db, user.id)
    result = await engine.execute_skill("mcp_character_planning", ai_client, {
        "title": proj.title, "genre": proj.genre or "网文", "theme": "",
        "time_period": "", "location": "", "world_info": world_info,
        "user_prompt": f"请为小说「{proj.title}」进行角色研究，提供角色设计建议。",
    })
    check_skill_error(result)
    return result.get("json") or {}
