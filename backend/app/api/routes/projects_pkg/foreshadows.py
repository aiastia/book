"""伏笔 + 剧情分析"""
import json
import difflib
from app.api.routes.projects_pkg.base import *


router = make_router()


# ============ 伏笔 ============
@router.get("/{project_id}/foreshadows")
async def list_foreshadows(project_id: int, status: str = None, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    service = ForeshadowService(db, project_id)
    fs_list = await service.list_all(status)
    return [{
        "id": f.id, "title": f.title, "content": f.content, "foreshadow_type": f.foreshadow_type,
        "status": f.status, "source_type": f.source_type,
        "plant_chapter_number": f.plant_chapter_number, "actual_plant_chapter": f.actual_plant_chapter,
        "target_resolve_chapter_number": f.target_resolve_chapter_number, "actual_resolve_chapter": f.actual_resolve_chapter,
        "priority": f.priority,
        "structure": f.structure or {},
    } for f in fs_list]


@router.post("/{project_id}/foreshadows")
async def create_foreshadow(project_id: int, req: ForeshadowCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    service = ForeshadowService(db, project_id)
    fs = await service.create(req.model_dump())
    return {"id": fs.id}


@router.put("/{project_id}/foreshadows/{foreshadow_id}")
async def update_foreshadow(project_id: int, foreshadow_id: int, req: ForeshadowCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    service = ForeshadowService(db, project_id)
    fs = await service.update(foreshadow_id, req.model_dump())
    if not fs:
        raise HTTPException(404, "伏笔不存在")
    return {"ok": True}


@router.delete("/{project_id}/foreshadows/{foreshadow_id}")
async def delete_foreshadow(project_id: int, foreshadow_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    service = ForeshadowService(db, project_id)
    if not await service.delete(foreshadow_id):
        raise HTTPException(404, "伏笔不存在")
    return {"ok": True}


@router.post("/{project_id}/foreshadows/plan")
async def plan_foreshadows(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """AI 自动规划伏笔"""
    await get_user_project(db, project_id, user)  # 权限校验
    outlines = (await db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.chapter_number))).scalars().all()
    if not outlines:
        raise HTTPException(400, "请先生成大纲")
    outlines_data = json.dumps([{
        "chapter_number": o.chapter_number, "title": o.title, "summary": o.summary,
        "key_points": o.key_points, "characters": o.characters,
    } for o in outlines], ensure_ascii=False)
    chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    chars_info = "\n".join([f"- {c.name}({c.role}): {c.personality[:100]}" for c in chars]) or "暂无"

    service = ForeshadowService(db, project_id)
    ai_client = await AIClient.from_user_config(db, user.id)
    created = await service.plan_foreshadows_from_outlines(ai_client, outlines_data, chars_info, user_id=user.id)
    return {"foreshadows": created, "count": len(created)}


# ===== #15 伏笔闭环操作 =====
class PlantReq(BaseModel):
    chapter_number: int
    hint_text: str = ""


@router.post("/{project_id}/foreshadows/{foreshadow_id}/plant")
async def plant_foreshadow(
    project_id: int, foreshadow_id: int, req: PlantReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """标记伏笔为已埋入。"""
    service = ForeshadowService(db, project_id)
    fs = await service.mark_as_planted(foreshadow_id, req.chapter_number, req.hint_text)
    if not fs:
        raise HTTPException(404, "伏笔不存在")
    return {"ok": True, "status": fs.status}


class ResolveReq(BaseModel):
    chapter_number: int
    resolution_text: str = ""
    is_partial: bool = False


@router.post("/{project_id}/foreshadows/{foreshadow_id}/resolve")
async def resolve_foreshadow(
    project_id: int, foreshadow_id: int, req: ResolveReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """标记伏笔为已回收。"""
    service = ForeshadowService(db, project_id)
    fs = await service.mark_as_resolved(foreshadow_id, req.chapter_number, req.resolution_text, req.is_partial)
    if not fs:
        raise HTTPException(404, "伏笔不存在")
    return {"ok": True, "status": fs.status}


class AbandonReq(BaseModel):
    reason: str = ""


@router.post("/{project_id}/foreshadows/{foreshadow_id}/abandon")
async def abandon_foreshadow(
    project_id: int, foreshadow_id: int, req: AbandonReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """放弃伏笔。"""
    service = ForeshadowService(db, project_id)
    fs = await service.mark_as_abandoned(foreshadow_id, req.reason)
    if not fs:
        raise HTTPException(404, "伏笔不存在")
    return {"ok": True, "status": fs.status}


@router.get("/{project_id}/foreshadows/pending-resolve")
async def pending_resolve(
    project_id: int, current_chapter: int = 1, lookahead: int = 5,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """获取待回收伏笔（含紧急度）。"""
    service = ForeshadowService(db, project_id)
    must = await service.get_must_resolve_foreshadows(current_chapter)
    upcoming = await service.get_pending_resolve_foreshadows(current_chapter, lookahead)
    overdue = await service.get_overdue_foreshadows(current_chapter)
    return {
        "must_resolve": [_fs_dict(f, current_chapter, service) for f in must],
        "upcoming": [_fs_dict(f, current_chapter, service) for f in upcoming],
        "overdue": [_fs_dict(f, current_chapter, service) for f in overdue],
    }


@router.get("/{project_id}/foreshadows/overdue")
async def overdue_foreshadows(
    project_id: int, current_chapter: int = 1,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """获取超期伏笔。"""
    service = ForeshadowService(db, project_id)
    overdue = await service.get_overdue_foreshadows(current_chapter)
    return [_fs_dict(f, current_chapter, service) for f in overdue]


class SyncReq(BaseModel):
    chapter_ids: Optional[list[int]] = None


@router.post("/{project_id}/foreshadows/sync-from-analysis")
async def sync_from_analysis(
    project_id: int, req: SyncReq,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """从剧情分析批量同步伏笔状态。"""
    service = ForeshadowService(db, project_id)
    result = await service.sync_from_analysis(project_id, req.chapter_ids, db)
    return result


def _fs_dict(f, current_chapter, service):
    """伏笔字典（含紧急度 + 扩展字段）。"""
    return {
        "id": f.id, "title": f.title, "content": f.content,
        "foreshadow_type": f.foreshadow_type, "status": f.status,
        "plant_chapter_number": f.plant_chapter_number,
        "actual_plant_chapter": f.actual_plant_chapter,
        "target_resolve_chapter_number": f.target_resolve_chapter_number,
        "actual_resolve_chapter": f.actual_resolve_chapter,
        "priority": f.priority,
        "structure": f.structure or {},
        "urgency_level": service.get_urgency_level(f, current_chapter),
    }


# ============ 剧情分析 ============
@router.get("/{project_id}/analyses")
async def list_analyses(project_id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    result = await db.execute(select(PlotAnalysis).where(PlotAnalysis.project_id == project_id).order_by(PlotAnalysis.chapter_number))
    return [{
        "id": a.id, "chapter_number": a.chapter_number, "plot_stage": a.plot_stage or "",
        "hooks": a.hooks, "foreshadows": a.foreshadows, "conflicts": a.conflicts,
        "conflict_types": a.conflict_types or [],
        "emotional_curve": a.emotional_curve or {},
        "quality_scores": a.quality_scores, "suggestions": a.suggestions,
        "dialogue_ratio": a.dialogue_ratio or 0, "description_ratio": a.description_ratio or 0,
        "pacing": a.pacing or "",
    } for a in result.scalars().all()]


@router.get("/{project_id}/analyses/{chapter_number}")
async def get_analysis(project_id: int, chapter_number: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    await get_user_project(db, project_id, user)  # 权限校验
    a = (await db.execute(select(PlotAnalysis).where(PlotAnalysis.project_id == project_id, PlotAnalysis.chapter_number == chapter_number).order_by(PlotAnalysis.id.desc()))).scalars().first()
    if not a:
        raise HTTPException(404, "分析不存在")
    return {
        "id": a.id, "chapter_number": a.chapter_number, "plot_stage": a.plot_stage or "",
        "hooks": a.hooks, "foreshadows": a.foreshadows, "conflicts": a.conflicts,
        "conflict_types": a.conflict_types or [],
        "emotion_curve": a.emotion_curve, "emotional_curve": a.emotional_curve or {},
        "character_states": a.character_states, "organization_states": a.organization_states or [],
        "key_plot_points": a.key_plot_points, "scenes": a.scenes,
        "pacing": a.pacing or "",
        "dialogue_ratio": a.dialogue_ratio or 0, "description_ratio": a.description_ratio or 0,
        "quality_scores": a.quality_scores, "suggestions": a.suggestions,
        "consistency_issues": a.consistency_issues or [],
        "analysis_report": a.analysis_report or "",
    }


# ===== #8 章节阅读器标注 =====
import re as _re

# 中文+英文标点（用于在正文里定位分析描述时容忍标点差异）
_PUNCT_RE = _re.compile(
    r"[，。！？、；：""''‘’“”\"'（）()\\[\\]【】《》<>「」『』\\-—…·~`!@#\$%\^&\*\+=\|\\/\?\.,;:\s]+"
)


def _locate_in_content(content: str, text: str) -> tuple[int, int]:
    """在正文里定位分析描述/原文引用，返回 (position, length)。

    多级匹配策略，从精确到模糊：
    1. 整段精确匹配（AI 给的 keyword/quote 通常是完整短句）
    2. 去标点后整段匹配（容忍中英文标点差异，如 ''vs""、……vs...）
    3. 切片精确匹配（描述前 N 字在正文里 find）
    4. 关键词匹配（提取中文短语逐个 find）
    5. 模糊匹配（最长片段包含）
    全失败返回 (-1, 0)。
    """
    if not text or not content:
        return -1, 0
    text = str(text).strip()
    if not text:
        return -1, 0

    # 1. 整段精确匹配
    pos = content.find(text)
    if pos >= 0:
        return pos, min(len(text), 60)

    # 2. 去标点后整段匹配（容忍标点差异）
    # 把中英文标点都剥掉，然后从正文里也剥标点后找位置，再映射回原始位置
    def _strip_punct(s: str) -> str:
        return _PUNCT_RE.sub("", s)
    text_clean = _strip_punct(text)
    if len(text_clean) >= 5:
        # 构造正文「剥标点字符」到「原位」的映射
        clean_chars = []
        idx_map = []  # clean_chars[i] 在原 content 的位置
        for i, ch in enumerate(content):
            if not _PUNCT_RE.match(ch):
                clean_chars.append(ch)
                idx_map.append(i)
        clean_content = "".join(clean_chars)
        cpos = clean_content.find(text_clean)
        if cpos >= 0 and cpos < len(idx_map):
            orig_start = idx_map[cpos]
            # 终点：用剥标点后的末尾位置映射回原文
            end_idx = min(cpos + len(text_clean) - 1, len(idx_map) - 1)
            orig_end = idx_map[end_idx] + 1
            return orig_start, max(1, orig_end - orig_start)

    # 3. 切片精确匹配（描述前 N 字直接 find）
    for n in (30, 20, 15, 10, 6):
        if len(text) >= n:
            pos = content.find(text[:n])
            if pos >= 0:
                return pos, min(len(text), 60)

    # 4. 关键词匹配：提取描述里的中文短语，逐个找
    phrases = [p for p in _PUNCT_RE.split(text) if 2 <= len(p) <= 10]
    for p in phrases:
        pos = content.find(p)
        if pos >= 0:
            return pos, min(len(p), 40)

    # 5. 模糊匹配：去标点后最长片段
    cleaned = [p for p in _PUNCT_RE.split(text) if len(p) >= 3]
    if cleaned:
        longest = max(cleaned, key=len)
        pos = content.find(longest)
        if pos >= 0:
            return pos, min(len(longest), 40)

    # 6. 最长公共子串匹配（比滑动窗口更精准，适合中文）
    if len(text) >= 3 and len(content) >= 5:
        sm = difflib.SequenceMatcher(None, text, content)
        match = sm.find_longest_match(0, len(text), 0, len(content))
        if match.size >= 3:  # 至少匹配3个字符
            return match.b, match.size
        # 如果最长匹配太短，尝试去掉所有标点后再找
        text_no_punct = _PUNCT_RE.sub("", text)
        content_no_punct = _PUNCT_RE.sub("", content)
        if text_no_punct != text and len(text_no_punct) >= 3:
            sm2 = difflib.SequenceMatcher(None, text_no_punct, content_no_punct)
            match2 = sm2.find_longest_match(0, len(text_no_punct), 0, len(content_no_punct))
            if match2.size >= 3:
                # 映射回原文位置：在 content_no_punct 中找 content 里的位置
                pos_in_stripped = match2.b
                orig_pos = 0
                stripped_pos = 0
                for i, ch in enumerate(content):
                    if stripped_pos >= pos_in_stripped:
                        orig_pos = i
                        break
                    if not _PUNCT_RE.match(ch):
                        stripped_pos += 1
                    orig_pos = i + 1
                return orig_pos, match2.size

    return -1, 0


@router.get("/{project_id}/chapters/{chapter_id}/annotations")
async def get_annotations(
    project_id: int, chapter_id: int,
    db: AsyncSession = Depends(get_db), user=Depends(get_current_user),
):
    """获取章节标注（用于阅读器高亮，来自剧情分析）。

    返回 {annotations, summary}。标注类型：hook/foreshadow/plot_point/character_event。
    每个标注含 position（字符偏移）、length、title、content、metadata、located（是否在正文定位到）。
    located=False 的标注在侧边栏显示但不在正文高亮。
    """
    chapter = (await db.execute(
        select(Chapter).where(Chapter.id == chapter_id, Chapter.project_id == project_id)
    )).scalar_one_or_none()
    if not chapter:
        raise HTTPException(404, "章节不存在")
    content = chapter.content or ""
    analysis = (await db.execute(
        select(PlotAnalysis).where(
            PlotAnalysis.chapter_id == chapter_id,
            PlotAnalysis.project_id == project_id,
        ).order_by(PlotAnalysis.id.desc())
    )).scalars().first()

    annotations = []
    if analysis:
        # 1. 钩子
        hooks = analysis.hooks or {}
        if isinstance(hooks, dict):
            for htype, htext in hooks.items():
                if not htext or not isinstance(htext, str):
                    continue
                pos, length = _locate_in_content(content, htext)
                annotations.append({
                    "type": "hook", "subtype": htype,
                    "title": f"钩子·{htype}", "content": htext,
                    "position": max(0, pos), "length": length,
                    "located": pos >= 0,
                })
        # 2. 伏笔
        for fs in (analysis.foreshadows or []):
            if not isinstance(fs, dict):
                continue
            title = fs.get("title", "")
            detail = fs.get("detail") or fs.get("content") or fs.get("description") or ""
            # 优先级：quote（正文原文引用）> keyword（AI 实际输出字段）> title/detail
            quote = fs.get("quote") or fs.get("keyword") or ""
            search_text = quote or title or detail
            pos, length = _locate_in_content(content, search_text)
            annotations.append({
                "type": "foreshadow",
                "subtype": fs.get("type", ""),
                "title": title or "伏笔", "content": detail or title,
                "position": max(0, pos), "length": length,
                "located": pos >= 0,
                "metadata": {"foreshadow_action": fs.get("type")},
            })
        # 3. 关键情节点
        for pp in (analysis.key_plot_points or []):
            if isinstance(pp, str):
                text = pp
                quote = ""
            else:
                text = pp.get("event") or pp.get("description") or pp.get("content") or ""
                # 优先用 quote / keyword（AI 实际输出字段）定位
                quote = pp.get("quote") or pp.get("keyword") or ""
            search_text = quote or text
            pos, length = _locate_in_content(content, search_text)
            annotations.append({
                "type": "plot_point", "title": "关键情节", "content": text or quote,
                "position": max(0, pos), "length": length,
                "located": pos >= 0,
            })
        # 4. 角色事件
        for cs in (analysis.character_states or []):
            if not isinstance(cs, dict):
                continue
            name = cs.get("character_name") or cs.get("character") or ""
            change = cs.get("mental_change") or cs.get("ability_change") or ""
            if not name:
                continue
            # 角色名定位：精确匹配 → 去姓匹配 → 单字匹配（处理 AI 用错名的情况，如霜璃↔苏璃）
            pos = content.find(name)
            if pos < 0 and len(name) >= 2:
                # 尝试去掉第一个字（姓）匹配
                pos = content.find(name[1:])
            if pos < 0 and len(name) >= 2:
                # 尝试任意两字组合
                for i in range(len(name) - 1):
                    sub = name[i:i+2]
                    pos = content.find(sub)
                    if pos >= 0:
                        break
            if pos < 0:
                # 最后用通用定位
                pos, _ = _locate_in_content(content, name)
            annotations.append({
                "type": "character_event",
                "title": f"{name} 状态变化", "content": change or cs.get("status", ""),
                "position": max(0, pos), "length": len(name) if pos >= 0 else 0,
                "located": pos >= 0,
                "metadata": {"character": name, "mental_change": change},
            })

    # 过滤：保留 located=True 的（正文高亮用），located=False 也保留（侧边栏显示）
    valid = [a for a in annotations if a["position"] < len(content)]
    located = [a for a in valid if a.get("located")]

    summary = {
        "total": len(valid),
        "located": len(located),
        "hooks": len([a for a in valid if a["type"] == "hook"]),
        "foreshadows": len([a for a in valid if a["type"] == "foreshadow"]),
        "plot_points": len([a for a in valid if a["type"] == "plot_point"]),
        "character_events": len([a for a in valid if a["type"] == "character_event"]),
        "has_analysis": analysis is not None,
    }
    return {"annotations": valid, "summary": summary}
