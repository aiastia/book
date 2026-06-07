"""批量章节生成服务（#12）。

对标 MuMuAINovel execute_batch_generation_in_order。
逐章顺序生成（前一章完成后才生成下一章），跨章上下文自动传递。
支持取消、重试、自动分析。
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.ai_client import AIClient
from app.models.batch_generation_task import BatchGenerationTask
from app.models.chapter import Chapter
from app.services.chapter_service import ChapterService

logger = logging.getLogger(__name__)


async def create_batch_task(
    user_id: int,
    project_id: int,
    chapter_ids: list[int],
    enable_analysis: bool = True,
    max_retries: int = 2,
    db: Optional[AsyncSession] = None,
) -> BatchGenerationTask:
    """创建批量生成任务（在请求 session 内调用）。"""
    async def _create(session):
        task = BatchGenerationTask(
            user_id=user_id,
            project_id=project_id,
            chapter_ids=chapter_ids,
            total_chapters=len(chapter_ids),
            enable_analysis=enable_analysis,
            max_retries=max_retries,
            status="pending",
            status_message="等待开始",
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        # 同步创建一条 BackgroundTask（让浮动面板能显示进度）
        from app.models.background_task import BackgroundTask
        bg = BackgroundTask(
            user_id=user_id, project_id=project_id,
            task_type="chapter_batch",
            title=f"批量生成 {len(chapter_ids)} 章",
            status="pending", progress=0, status_message="等待开始",
            payload={"batch_task_id": task.id},
        )
        session.add(bg)
        await session.commit()
        await session.refresh(bg)
        return task

    if db is not None:
        return await _create(db)
    async with async_session() as session:
        return await _create(session)


async def get_batch_task(task_id: int) -> Optional[dict]:
    async with async_session() as db:
        task = (await db.execute(
            select(BatchGenerationTask).where(BatchGenerationTask.id == task_id)
        )).scalar_one_or_none()
        return task.to_dict() if task else None


async def cancel_batch_task(task_id: int, user_id: int) -> bool:
    async with async_session() as db:
        task = (await db.execute(
            select(BatchGenerationTask).where(
                BatchGenerationTask.id == task_id,
                BatchGenerationTask.user_id == user_id,
            )
        )).scalar_one_or_none()
        if not task:
            return False
        if task.status in ("pending", "running"):
            task.cancel_requested = True
            if task.status == "pending":
                task.status = "cancelled"
                task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            await db.commit()
        return True


async def list_active_batch_tasks(user_id: int, project_id: Optional[int] = None) -> list[dict]:
    async with async_session() as db:
        q = select(BatchGenerationTask).where(
            BatchGenerationTask.user_id == user_id,
            BatchGenerationTask.status.in_(["pending", "running"]),
        )
        if project_id:
            q = q.where(BatchGenerationTask.project_id == project_id)
        rows = (await db.execute(q)).scalars().all()
        return [t.to_dict() for t in rows]


async def run_batch_generation(task_id: int):
    """批量顺序生成（后台协程，独立 session）。

    流程：
    1. 加载任务，标记 running
    2. 逐章循环：
       a. 检查取消
       b. 若章节已有内容（已生成）→ 跳过
       c. 调 ChapterService.generate_chapter
       d. 失败重试（max_retries 次）
       e. 更新进度
    3. 全部完成 → completed
    """
    async with async_session() as db:
        task = (await db.execute(
            select(BatchGenerationTask).where(BatchGenerationTask.id == task_id)
        )).scalar_one_or_none()
        if not task:
            return
        if task.status not in ("pending", "running"):
            return

        user_id = task.user_id
        project_id = task.project_id
        chapter_ids = task.chapter_ids or []
        enable_analysis = task.enable_analysis
        max_retries = task.max_retries

        # 标记开始
        task.status = "running"
        task.started_at = datetime.utcnow()
        task.status_message = "开始批量生成"
        await db.commit()

    failed = []
    completed = 0
    ai_client = None

    for idx, chapter_id in enumerate(chapter_ids):
        # 检查取消
        async with async_session() as check_db:
            t = (await check_db.execute(
                select(BatchGenerationTask.cancel_requested, BatchGenerationTask.status)
                .where(BatchGenerationTask.id == task_id)
            )).first()
            if not t or t[0] or t[1] == "cancelled":
                logger.info(f"[batch] 任务 {task_id} 已取消")
                await _mark_status(task_id, "cancelled", f"已取消（完成 {completed}/{len(chapter_ids)}）")
                return

        # 独立 session 处理单章
        success = False
        last_err = ""
        for attempt in range(max_retries + 1):
            try:
                async with async_session() as chap_db:
                    # 获取章节信息
                    chapter = (await chap_db.execute(
                        select(Chapter).where(Chapter.id == chapter_id)
                    )).scalar_one_or_none()
                    if not chapter:
                        last_err = f"章节 {chapter_id} 不存在"
                        break
                    ch_num = chapter.chapter_number

                    # 更新当前进度
                    await _update_progress(task_id, idx, chapter_id, ch_num, attempt,
                                           f"生成第{ch_num}章" + (f"（重试 {attempt}）" if attempt else ""))

                    # 若已有内容则跳过
                    if chapter.content and len(chapter.content.strip()) > 100:
                        logger.info(f"[batch] 第{ch_num}章已有内容，跳过")
                        completed += 1
                        success = True
                        break

                    # 获取 AI 客户端（首次创建后复用）
                    if ai_client is None:
                        ai_client = await AIClient.from_user_config(chap_db, user_id)

                    # 调章节服务生成
                    svc = ChapterService(chap_db, project_id, user_id)
                    result = await svc.generate_chapter(chapter_id, ai_client)
                    if result.get("error"):
                        last_err = result["error"]
                        logger.warning(f"[batch] 第{ch_num}章生成失败（尝试 {attempt+1}）: {last_err}")
                        await asyncio.sleep(2)  # 重试间隔
                        continue
                    success = True
                    completed += 1
                    logger.info(f"[batch] 第{ch_num}章生成完成 ({completed}/{len(chapter_ids)})")
                    break
            except Exception as e:
                last_err = str(e)
                logger.warning(f"[batch] 第{chapter_id}章异常（尝试 {attempt+1}）: {e}")
                await asyncio.sleep(2)

        if not success:
            # 记录失败章节
            async with async_session() as fdb:
                ch = (await fdb.execute(select(Chapter).where(Chapter.id == chapter_id))).scalar_one_or_none()
                failed.append({
                    "chapter_id": chapter_id,
                    "chapter_number": ch.chapter_number if ch else None,
                    "error": last_err[:300],
                })
                await fdb.execute(
                    update(BatchGenerationTask).where(BatchGenerationTask.id == task_id).values(
                        failed_chapters=failed,
                        completed_chapters=completed,
                        updated_at=datetime.utcnow(),
                    )
                )
                await fdb.commit()
            logger.error(f"[batch] 第{chapter_id}章最终失败: {last_err}")
            # 任一章失败 → 终止后续（对标 MuMu 不跳过）
            await _mark_status(task_id, "failed",
                               f"第{chapter_id}章生成失败: {last_err[:200]}", error=last_err[:2000])
            return

        # 更新完成数
        async with async_session() as pdb:
            progress = int((completed / len(chapter_ids)) * 100) if chapter_ids else 100
            await pdb.execute(
                update(BatchGenerationTask).where(BatchGenerationTask.id == task_id).values(
                    completed_chapters=completed,
                    progress=min(99, progress),
                    updated_at=datetime.utcnow(),
                )
            )
            await pdb.commit()

    # 全部完成
    await _mark_status(task_id, "completed",
                       f"批量完成（{completed}/{len(chapter_ids)} 章）")


async def _update_progress(task_id, idx, chapter_id, ch_num, attempt, message):
    async with async_session() as db:
        # 更新 BatchGenerationTask
        await db.execute(
            update(BatchGenerationTask).where(BatchGenerationTask.id == task_id).values(
                current_index=idx,
                current_chapter_id=chapter_id,
                current_chapter_number=ch_num,
                current_retry_count=attempt,
                status_message=message[:500],
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()
    # 同步更新 BackgroundTask（浮动面板用）
    await _sync_bg_task(task_id, message, progress=None)


async def _sync_bg_task(batch_task_id: int, message: str, progress: int = None):
    """同步更新 BackgroundTask（浮动面板查的表）。"""
    async with async_session() as db:
        from app.models.background_task import BackgroundTask
        bg = (await db.execute(
            select(BackgroundTask).where(
                BackgroundTask.payload.like(f'%"batch_task_id": {batch_task_id}%')
            )
        )).scalars().first()
        if bg:
            values = {"status_message": message[:500], "status": "running", "updated_at": datetime.utcnow()}
            if progress is not None:
                values["progress"] = min(99, max(0, progress))
            await db.execute(
                update(BackgroundTask).where(BackgroundTask.id == bg.id).values(**values)
            )
            await db.commit()


async def _mark_status(task_id, status, message, error=""):
    async with async_session() as db:
        values = {
            "status": status,
            "status_message": message[:500],
            "updated_at": datetime.utcnow(),
        }
        if status in ("completed", "failed", "cancelled"):
            values["completed_at"] = datetime.utcnow()
            if status == "completed":
                values["progress"] = 100
        if error:
            values["error"] = error
        await db.execute(
            update(BatchGenerationTask).where(BatchGenerationTask.id == task_id).values(**values)
        )
        await db.commit()
    # 同步 BackgroundTask
    await _sync_bg_task(task_id, message, progress=100 if status == "completed" else None)
    # 更新 BackgroundTask 的最终状态
    async with async_session() as db:
        from app.models.background_task import BackgroundTask
        bg = (await db.execute(
            select(BackgroundTask).where(
                BackgroundTask.payload.like(f'%"batch_task_id": {task_id}%')
            )
        )).scalars().first()
        if bg:
            bg.status = status
            bg.status_message = message[:500]
            if status == "completed":
                bg.progress = 100
            if error:
                bg.error = error[:2000]
            if status in ("completed", "failed", "cancelled"):
                bg.completed_at = datetime.utcnow()
            await db.commit()
