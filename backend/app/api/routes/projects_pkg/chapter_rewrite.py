"""章节重写路由（#11 重写历史 + #13 扩写缩写/局部重写）。

提供：
- 整章重写（基于修改指令 + 长度模式 + 聚焦领域）
- 重写历史列表 + 版本对比
- 应用重写结果（覆盖章节）
- 局部重写（选中片段重写）+ 应用
"""

import difflib
import logging

from app.api.routes.projects_pkg.base import *
from app.models.chapter import Chapter
from app.models.outline import Outline
from app.models.regeneration_task import RegenerationTask

logger = logging.getLogger(__name__)
router = make_router()


class RegenerateReq(BaseModel):
    modification_instructions: str = ""
    focus_areas: list[str] = []  # pacing/emotion/description/dialogue/conflict
    preserve_elements: list[str] = []
    length_mode: str = "similar"  # similar/expand/condense/custom
    target_word_count: Optional[int] = None
    version_note: str = ""


def _calc_word_range(orig_count: int, length_mode: str, target: Optional[int]) -> tuple[int, int]:
    """根据长度模式计算目标字数区间（#13）。"""
    if length_mode == "expand":
        return int(orig_count * 1.3), int(orig_count * 2.0)
    if length_mode == "condense":
        return int(orig_count * 0.5), int(orig_count * 0.8)
    if length_mode == "custom" and target:
        return int(target * 0.85), int(target * 1.15)
    # similar
    return int(orig_count * 0.85), int(orig_count * 1.2)


FOCUS_DESC = {
    "pacing": "节奏（快慢张弛）",
    "emotion": "情感表达（更细腻/更克制）",
    "description": "场景描写（更生动/更精简）",
    "dialogue": "对话（更自然/更有个性）",
    "conflict": "冲突张力（更激烈/更压抑）",
}


def _build_rewrite_prompt(chapter: Chapter, outline: Outline, req: RegenerateReq, project) -> str:
    """组装重写提示词。"""
    orig_count = len(chapter.content or "")
    min_words, max_words = _calc_word_range(orig_count, req.length_mode, req.target_word_count)
    focus_text = (
        "、".join(FOCUS_DESC.get(f, f) for f in req.focus_areas) if req.focus_areas else "整体提升"
    )
    preserve_text = (
        "\n".join(f"- {p}" for p in req.preserve_elements)
        if req.preserve_elements
        else "无特殊要求"
    )

    return f"""你是资深网文编辑。请重写以下章节内容。

重写要求：
1. 聚焦领域：{focus_text}
2. 修改指令：{req.modification_instructions or "根据聚焦领域优化"}
3. 长度模式：{req.length_mode}（目标 {min_words}-{max_words} 字）
4. 必须保留的元素：
{preserve_text}
5. 保持原有剧情走向、人设、关键事件不变
6. {("扩写：增加细节、心理、环境描写，丰富层次" if req.length_mode == "expand" else "")}
   {("精简：删除冗余，加快节奏，保留核心" if req.length_mode == "condense" else "")}
   {("保持相似长度，优化质量" if req.length_mode == "similar" else "")}

小说：《{project.title}》（{project.genre or "网文"}）
章节：第{chapter.chapter_number}章 {chapter.title}
大纲：{outline.summary if outline else "（无）"}

原始内容（{orig_count}字）：
{chapter.content}

请直接输出重写后的完整章节正文（不要任何说明、不要 markdown 代码块、不要标题）："""


@router.post("/{project_id}/chapters/{chapter_id}/regenerate")
async def regenerate_chapter(
    project_id: int,
    chapter_id: int,
    req: RegenerateReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """整章重写（#11 #13）。保存版本快照，返回重写结果。"""
    project = await get_user_project(db, project_id, user)
    chapter = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    if not chapter.content or len(chapter.content.strip()) < 50:
        raise HTTPException(400, "章节内容过少，无法重写")

    outline = None
    if chapter.outline_id:
        outline = (
            await db.execute(select(Outline).where(Outline.id == chapter.outline_id))
        ).scalar_one_or_none()

    # 计算下一版本号
    existing_count = (
        (
            await db.execute(
                select(RegenerationTask).where(RegenerationTask.chapter_id == chapter_id)
            )
        )
        .scalars()
        .all()
    )
    next_version = len(existing_count) + 1

    # 原文快照
    original_content = chapter.content
    original_count = len(original_content)

    # 创建任务记录
    task = RegenerationTask(
        user_id=user.id,
        project_id=project_id,
        chapter_id=chapter_id,
        modification_instructions=req.modification_instructions,
        focus_areas=req.focus_areas,
        preserve_elements=req.preserve_elements,
        length_mode=req.length_mode,
        target_word_count=req.target_word_count,
        original_content=original_content,
        original_word_count=original_count,
        version_number=next_version,
        version_note=req.version_note,
        status="running",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 调 AI 重写（使用公用 skill 的 system prompt，user_prompt 携带具体指令）
    engine, ai_client = await make_engine_and_client(db, user.id)
    prompt = _build_rewrite_prompt(chapter, outline, req, project)
    result = await engine.execute_skill(
        "chapter_full_rewrite",
        ai_client,
        {
            "user_prompt": prompt,
        },
    )
    if result.get("error"):
        task.status = "failed"
        task.error = result["error"]
        await db.commit()
        raise HTTPException(500, f"重写失败: {result['error']}")

    new_content = (result.get("content") or "").strip()
    # 清理 AI 常见前缀
    for prefix in ["重写后：", "以下是重写后的内容：", "```", "重写内容："]:
        if new_content.startswith(prefix):
            new_content = new_content[len(prefix) :].strip()
    if new_content.startswith("```"):
        new_content = new_content.split("\n", 1)[-1] if "\n" in new_content else new_content
    if new_content.endswith("```"):
        new_content = new_content[:-3].strip()

    task.regenerated_content = new_content
    task.regenerated_word_count = len(new_content)
    task.status = "completed"
    await db.commit()
    await db.refresh(task)

    return task.to_dict()


@router.get("/{project_id}/chapters/{chapter_id}/regeneration/tasks")
async def list_regen_tasks(
    project_id: int,
    chapter_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """重写历史列表（#11）。"""
    await get_user_project(db, project_id, user)
    tasks = (
        (
            await db.execute(
                select(RegenerationTask)
                .where(
                    RegenerationTask.chapter_id == chapter_id,
                    RegenerationTask.project_id == project_id,
                )
                .order_by(RegenerationTask.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [t.to_dict() for t in tasks]


@router.get("/{project_id}/chapters/{chapter_id}/regeneration/{task_id}")
async def get_regen_task(
    project_id: int,
    chapter_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """获取重写任务详情（含原文/重写文，用于对比）。"""
    await get_user_project(db, project_id, user)
    task = (
        await db.execute(
            select(RegenerationTask).where(
                RegenerationTask.id == task_id,
                RegenerationTask.chapter_id == chapter_id,
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "重写任务不存在")
    return {
        **task.to_dict(),
        "original_content": task.original_content or "",
        "regenerated_content": task.regenerated_content or "",
        "diff_ratio": _calc_diff(task.original_content or "", task.regenerated_content or ""),
    }


def _calc_diff(original: str, new: str) -> float:
    """计算相似度（0-1）。"""
    if not original or not new:
        return 0.0
    return round(difflib.SequenceMatcher(None, original, new).ratio(), 3)


@router.post("/{project_id}/chapters/{chapter_id}/regeneration/{task_id}/apply")
async def apply_regen(
    project_id: int,
    chapter_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """应用重写结果（覆盖章节内容）。"""
    await get_user_project(db, project_id, user)
    task = (
        await db.execute(
            select(RegenerationTask).where(
                RegenerationTask.id == task_id,
                RegenerationTask.chapter_id == chapter_id,
            )
        )
    ).scalar_one_or_none()
    if not task:
        raise HTTPException(404, "重写任务不存在")
    if task.status != "completed":
        raise HTTPException(400, "重写任务未完成")
    chapter = (
        await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    chapter.content = task.regenerated_content
    chapter.word_count = task.regenerated_word_count
    task.is_applied = 1
    await db.commit()
    return {"ok": True, "word_count": task.regenerated_word_count}


# ===== #13 局部重写 =====
class PartialRegenReq(BaseModel):
    selected_text: str
    start_position: int = 0  # 在原文中的字符偏移
    end_position: int = 0
    instructions: str = ""
    length_mode: str = "similar"  # similar/expand/condense


@router.post("/{project_id}/chapters/{chapter_id}/partial-regenerate")
async def partial_regenerate(
    project_id: int,
    chapter_id: int,
    req: PartialRegenReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """局部重写：只重写选中的片段（#13）。"""
    project = await get_user_project(db, project_id, user)
    chapter = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    if not req.selected_text.strip():
        raise HTTPException(400, "请选择要重写的文本片段")

    content = chapter.content or ""
    sel = req.selected_text
    orig_count = len(sel)
    min_w, max_w = _calc_word_range(orig_count, req.length_mode, None)

    # 取上下文（前后各 300 字）
    start = (
        max(0, req.start_position - 300) if req.start_position else max(0, content.find(sel) - 300)
    )
    ctx_before = (
        content[start : req.start_position]
        if req.start_position
        else content[max(0, content.find(sel) - 300) : content.find(sel)]
    )
    sel_pos = content.find(sel)
    end_pos = sel_pos + len(sel) if sel_pos >= 0 else len(content)
    ctx_after = content[end_pos : min(len(content), end_pos + 300)]

    engine, ai_client = await make_engine_and_client(db, user.id)
    prompt = f"""你是网文编辑。请只重写以下选中的片段，保持与上下文衔接自然。

【前文】
{ctx_before}

【需要重写的片段】（{orig_count}字）
{sel}

【后文】
{ctx_after}

重写要求：
1. {req.instructions or "优化表达，提升质量"}
2. 长度模式：{req.length_mode}（目标 {min_w}-{max_w} 字）
3. 必须与前后文衔接自然，语气风格一致
4. 只输出重写后的片段内容（不要包含前文后文，不要说明，不要 markdown）

请直接输出："""
    result = await engine.execute_skill(
        "partial_regenerate",
        ai_client,
        {
            "user_prompt": prompt,
        },
    )
    if result.get("error"):
        raise HTTPException(500, f"局部重写失败: {result['error']}")
    new_text = (result.get("content") or "").strip()
    for prefix in ["重写后：", "以下是重写：", "```"]:
        if new_text.startswith(prefix):
            new_text = new_text[len(prefix) :].strip()
    if new_text.endswith("```"):
        new_text = new_text[:-3].strip()

    return {
        "original_text": sel,
        "regenerated_text": new_text,
        "start_position": sel_pos if sel_pos >= 0 else req.start_position,
        "end_position": (sel_pos + len(sel)) if sel_pos >= 0 else req.end_position,
        "original_length": orig_count,
        "regenerated_length": len(new_text),
    }


class ApplyPartialReq(BaseModel):
    new_text: str
    start_position: int
    end_position: int


@router.post("/{project_id}/chapters/{chapter_id}/apply-partial-regenerate")
async def apply_partial(
    project_id: int,
    chapter_id: int,
    req: ApplyPartialReq,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """应用局部重写（替换原文片段）。"""
    await get_user_project(db, project_id, user)
    chapter = (
        await db.execute(
            select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
        )
    ).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    content = chapter.content or ""
    new_content = content[: req.start_position] + req.new_text + content[req.end_position :]
    chapter.content = new_content
    chapter.word_count = len(new_content)
    await db.commit()
    return {"ok": True, "word_count": len(new_content)}
