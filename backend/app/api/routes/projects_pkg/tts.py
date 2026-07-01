"""章节 TTS:小说正文 → Director 分析 → SSML。

挂在项目路由下,路径为 /api/projects/{project_id}/chapters/{chapter_id}/tts。
复用墨语 AIClient(用户配置的模型/base_url/key),不另起 LLM 客户端。

采用后台任务模式:立即返回 task_id,后台跑 Director + Builder,
完成后结果存在 task.result 里,前端轮询拿。
"""

from datetime import datetime

from app.api.routes.projects_pkg.base import *  # noqa: F401,F403
from app.services.tts_pipeline.director import Director
from app.services.tts_pipeline.builder import SSMLBuilder
from app.services.tts_pipeline.models import DirectorLine, SceneChange
from app.services.async_ai_service import submit_async_task
from app.services import background_task_service as bg_service

router = make_router()  # noqa: F405  prefix=/api/projects


class TtsConvertRequest(BaseModel):  # noqa: F405
    """章节转 SSML 请求。"""
    voice: str = "zh-CN-XiaoxiaoNeural"
    chunk_size: int = 1500
    model: str | None = None  # 指定模型(空=用用户默认模型)
    # 可选:自定义角色/场景配置(覆盖默认 YAML)
    characters: dict | None = None
    scenes: dict | None = None


class TtsBuildRequest(BaseModel):  # noqa: F405
    """用已有 Director JSON 直接拼 SSML(跳过 LLM)。"""
    director_json: list
    voice: str = "zh-CN-XiaoxiaoNeural"
    characters: dict | None = None
    scenes: dict | None = None


def _instructions_to_json(instructions) -> list:
    result = []
    for instr in instructions:
        if isinstance(instr, SceneChange):
            result.append({"scene_change": instr.scene_change})
        elif isinstance(instr, DirectorLine):
            result.append({
                "speaker": instr.speaker,
                "text": instr.text,
                "emotion": instr.emotion,
                "pause_after": instr.pause_after,
            })
    return result


@router.post("/{project_id}/chapters/{chapter_id}/tts")
async def chapter_to_ssml(
    project_id: int,
    chapter_id: int,
    req: TtsConvertRequest,
    db: AsyncSession = Depends(get_db),  # noqa: F405
    user=Depends(get_current_user),  # noqa: F405
):
    """把指定章节的正文转成 SSML(后台任务,立即返回 task_id)。"""
    # 权限校验 + 取章节
    await get_user_project(db, project_id, user)  # noqa: F405
    result = await db.execute(
        select(Chapter).where(  # noqa: F405
            Chapter.id == chapter_id,  # noqa: F405
            Chapter.project_id == project_id,  # noqa: F405
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")  # noqa: F405

    if not chapter.content or not chapter.content.strip():
        raise HTTPException(400, "章节内容为空")  # noqa: F405

    ch_title = chapter.title or f"第{chapter.chapter_number}章"
    ch_content = chapter.content  # 快照,避免后续 session 变化

    async def _run_tts(task_id: int, payload: dict, db: AsyncSession):
        tracker = bg_service.TaskProgressTracker(task_id, db=db)
        if await tracker.is_cancelled():
            await tracker.cancel("用户取消")
            return

        await tracker.update(stage="preparing", message="正在初始化 AI 客户端...")

        _, ai_client = await make_engine_and_client(  # noqa: F405
            db, payload["user_id"], model_override=payload.get("model") or None
        )

        await tracker.update(
            stage="analyzing",
            message=f"导演分析中({len(payload['content'])} 字,可能需要 1-2 分钟)...",
        )

        # ① Director 分析
        director = Director(ai_client=ai_client, chunk_size=payload.get("chunk_size", 1500))
        instructions, err = await director.analyze(payload["content"])
        if err:
            await tracker.fail(f"导演分析失败: {err}")
            return

        await tracker.update(stage="building", message="正在拼接 SSML...")

        # ② Builder 拼 SSML
        try:
            builder = SSMLBuilder(
                characters_override=payload.get("characters"),
                scenes_override=payload.get("scenes"),
            )
            ssml_parts = builder.build(instructions, voice=payload.get("voice", "zh-CN-XiaoxiaoNeural"))
        except ValueError as e:
            await tracker.fail(f"SSML 构建失败(配置错误): {str(e)}")
            return

        line_count = sum(1 for i in instructions if isinstance(i, DirectorLine))
        scene_count = sum(1 for i in instructions if isinstance(i, SceneChange))

        # 持久化到章节表（任务记录被清理也不丢）
        tts_data = {
            "success": True,
            "ssml_parts": ssml_parts,
            "director_json": _instructions_to_json(instructions),
            "stats": {
                "lines": line_count,
                "scenes": scene_count,
                "chars": len(payload["content"]),
                "ssml_parts": len(ssml_parts),
            },
            "created_at": datetime.utcnow().isoformat(),
        }
        ch = await db.execute(
            select(Chapter).where(Chapter.id == payload["chapter_id"])  # noqa: F405
        )
        ch_obj = ch.scalar_one_or_none()
        if ch_obj:
            ch_obj.ssml_result = tts_data

        await tracker.complete(
            result=tts_data,
            message=f"语音转换完成({line_count} 句,{len(ssml_parts)} 段 SSML)",
        )

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="chapter_tts",
        title=f"转语音: {ch_title}",
        payload={
            "chapter_id": chapter_id,
            "user_id": user.id,
            "content": ch_content,
            "voice": req.voice,
            "model": req.model,
            "chunk_size": req.chunk_size,
            "characters": req.characters,
            "scenes": req.scenes,
        },
        runner=_run_tts,
    )
    return {"task_id": task_id, "chapter_id": chapter_id}


@router.post("/{project_id}/chapters/{chapter_id}/tts/build")
async def chapter_ssml_build_only(
    project_id: int,
    chapter_id: int,
    req: TtsBuildRequest,
    db: AsyncSession = Depends(get_db),  # noqa: F405
    user=Depends(get_current_user),  # noqa: F405
):
    """用已有 Director JSON 直接拼 SSML(不调 LLM,同步)。用于微调后重建。"""
    await get_user_project(db, project_id, user)  # noqa: F405

    instructions = _parse_instructions(req.director_json)
    if not instructions:
        raise HTTPException(400, "director_json 为空或格式不对")  # noqa: F405

    try:
        builder = SSMLBuilder(characters_override=req.characters, scenes_override=req.scenes)
        ssml_parts = builder.build(instructions, voice=req.voice)
    except ValueError as e:
        return {"success": False, "error": f"配置错误: {str(e)}"}

    return {"success": True, "ssml_parts": ssml_parts, "stats": {"ssml_parts": len(ssml_parts)}}


def _parse_instructions(raw_list: list):
    instructions = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        if "scene_change" in item:
            instructions.append(SceneChange(scene_change=str(item["scene_change"])))
        elif "text" in item:
            instructions.append(DirectorLine(
                speaker=str(item.get("speaker", "Narrator")),
                text=str(item["text"]),
                emotion=item.get("emotion"),
                pause_after=item.get("pause_after"),
            ))
    return instructions
