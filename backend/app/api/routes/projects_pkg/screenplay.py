"""章节分镜：小说正文 → Director 分析 → 分镜剧本（Screenplay）。

挂在项目路由下，路径为 /api/projects/{project_id}/chapters/{chapter_id}/screenplay。
复用墨语 AIClient（用户配置的模型/base_url/key）。

模式 B（分离关注点）：
  ① Director 分析音频维度（speaker/emotion/scene/pause）—— 复用现有 tts_pipeline
  ② Screenwriter 补充画面维度（shot_type/action/visual_prompt/duration/sfx）

采用后台任务模式：立即返回 task_id，后台跑 Director + Screenwriter，
完成后结果存在 chapter.screenplay_result 里，前端轮询拿。
"""

from datetime import datetime

from app.api.routes.projects_pkg.base import *  # noqa: F401,F403
from app.services.tts_pipeline.director import Director
from app.services.tts_pipeline.models import DirectorLine, SceneChange
from app.services.screenwriter.screenwriter import (
    Screenwriter,
    screenplay_to_json,
    screenplay_stats,
)
from app.services.async_ai_service import submit_async_task
from app.services import background_task_service as bg_service

router = make_router()  # noqa: F405  prefix=/api/projects


class ScreenplayRequest(BaseModel):  # noqa: F405
    """生成分镜剧本请求。"""
    chunk_size: int = 1500           # Director 分块大小
    screenplay_chunk_size: int = 1500  # Screenwriter 分块大小（画面分析需要更大上下文）
    model: str | None = None         # 指定模型（空=用用户默认模型）


@router.post("/{project_id}/chapters/{chapter_id}/screenplay")
async def generate_screenplay(
    project_id: int,
    chapter_id: int,
    req: ScreenplayRequest,
    db: AsyncSession = Depends(get_db),  # noqa: F405
    user=Depends(get_current_user),  # noqa: F405
):
    """把指定章节生成带画面维度的分镜剧本（后台任务，立即返回 task_id）。

    流程（模式 B）：
      ① Director：原文 → 音频维度（speaker/emotion/scene/pause）
      ② Screenwriter：原文 + Director 结果 → 画面维度（shot_type/action/visual_prompt/duration/sfx）

    最终产物存入 chapter.screenplay_result，供后续视频生成流程使用。
    """
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
    ch_content = chapter.content  # 快照

    async def _run_screenplay(task_id: int, payload: dict, db: AsyncSession):
        tracker = bg_service.TaskProgressTracker(task_id, db=db)
        if await tracker.is_cancelled():
            await tracker.cancel("用户取消")
            return

        await tracker.update(stage="preparing", message="正在初始化 AI 客户端...")

        _, ai_client = await make_engine_and_client(  # noqa: F405
            db, payload["user_id"], model_override=payload.get("model") or None
        )

        content = payload["content"]

        # ── ① Director 分析（音频维度）──
        await tracker.update(
            stage="directing",
            message=f"导演分析中（{len(content)} 字，可能需要 1-2 分钟）...",
        )

        director = Director(
            ai_client=ai_client,
            chunk_size=payload.get("chunk_size", 1500),
        )
        instructions, err = await director.analyze(content)
        if err:
            await tracker.fail(f"导演分析失败: {err}")
            return

        line_count = sum(1 for i in instructions if isinstance(i, DirectorLine))
        scene_count = sum(1 for i in instructions if isinstance(i, SceneChange))
        await tracker.update(
            stage="directing_done",
            progress=50,
            message=f"导演分析完成（{line_count} 句，{scene_count} 个场景切换），开始分镜...",
        )

        # ── ② Screenwriter 分析（画面维度）──
        screenwriter = Screenwriter(
            ai_client=ai_client,
            chunk_size=payload.get("screenplay_chunk_size", 1500),
        )
        screenplay, err = await screenwriter.generate(content, instructions)
        if err:
            await tracker.fail(f"分镜分析失败: {err}")
            return

        # 统计 + 序列化
        stats = screenplay_stats(screenplay)
        shots_json = screenplay_to_json(screenplay)

        screenplay_data = {
            "success": True,
            "shots": shots_json,
            "stats": stats,
            "director_stats": {
                "lines": line_count,
                "scenes": scene_count,
                "chars": len(content),
            },
            "created_at": datetime.utcnow().isoformat(),
        }

        # 持久化到章节表
        ch = await db.execute(
            select(Chapter).where(Chapter.id == payload["chapter_id"])  # noqa: F405
        )
        ch_obj = ch.scalar_one_or_none()
        if ch_obj:
            ch_obj.screenplay_result = screenplay_data

        await tracker.complete(
            result=screenplay_data,
            message=(
                f"分镜完成：{stats['shot_count']} 个镜头，"
                f"预计时长 {stats['total_duration_display']}，"
                f"{stats['scene_count']} 个场景"
            ),
        )

    task_id = await submit_async_task(
        user_id=user.id,
        project_id=project_id,
        task_type="chapter_screenplay",
        title=f"分镜: {ch_title}",
        payload={
            "chapter_id": chapter_id,
            "user_id": user.id,
            "content": ch_content,
            "model": req.model,
            "chunk_size": req.chunk_size,
            "screenplay_chunk_size": req.screenplay_chunk_size,
        },
        runner=_run_screenplay,
    )
    return {"task_id": task_id, "chapter_id": chapter_id}


@router.get("/{project_id}/chapters/{chapter_id}/screenplay")
async def get_screenplay(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),  # noqa: F405
    user=Depends(get_current_user),  # noqa: F405
):
    """获取已生成的分镜剧本（从 chapter.screenplay_result 读取）。"""
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

    if not chapter.screenplay_result:
        raise HTTPException(404, "尚未生成分镜剧本")  # noqa: F405

    return chapter.screenplay_result
