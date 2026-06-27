"""墨鱼写作系统 · 工具层

每个函数封装一个 API 操作。AI 调用这些函数，不需要了解 HTTP/认证/轮询。

用法:
    from app.tools.api import BookAPI
    api = BookAPI("https://moyu.example.com/api")
    await api.login("user", "pass")
    book = await api.create_book("仙王", genre="玄幻", outline_mode="one_to_many")
    await api.generate_chapter(book["id"], start=1, count=3)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BookAPI:
    """墨鱼写作系统 API 客户端。所有操作通过此对象调用。"""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")
        self.token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(600))

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ============================================================
    # 认证
    # ============================================================

    async def login(self, username: str, password: str) -> dict:
        """登录获取 token。返回用户信息。"""
        await self._ensure_client()
        r = await self._client.post(
            f"{self.base}/login",
            json={"username": username, "password": password},
        )
        if r.status_code == 401:
            raise PermissionError("用户名或密码错误")
        r.raise_for_status()
        data = r.json()
        self.token = data["access_token"]
        return data.get("user", {})

    # ============================================================
    # HTTP 基础
    # ============================================================

    async def _request(
        self, method: str, path: str, json_body: dict | None = None
    ) -> dict:
        """发送 API 请求。自动附加 token，401 时抛出异常提示重新登录。"""
        await self._ensure_client()
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        url = f"{self.base}{path}"
        r = await self._client.request(method, url, json=json_body, headers=headers)
        if r.status_code == 401:
            raise PermissionError("Token 过期，请重新 login()")
        if r.status_code >= 400:
            detail = ""
            try:
                detail = r.json().get("detail", r.text[:200])
            except Exception:
                detail = r.text[:200]
            raise RuntimeError(f"API 错误 {r.status_code}: {detail}")
        if not r.text.strip():
            return {}
        return r.json()

    async def _poll_async(
        self,
        task_result: dict,
        poll_path_fmt: str,
        status_field: str = "status",
        done_values: tuple = ("completed", "failed", "cancelled"),
        interval: int = 5,
        timeout: int = 600,
    ) -> dict:
        """轮询异步任务直到完成或超时。返回最终状态。"""
        task_id = task_result.get("task_id")
        if not task_id:
            return task_result

        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            try:
                st = await self._request("GET", poll_path_fmt.format(task_id=task_id))
                status = st.get(status_field, "")
                if status in done_values:
                    return st
            except Exception as e:
                logger.warning(f"轮询 {task_id} 失败: {e}")
        raise TimeoutError(f"任务 {task_id} 在 {timeout}s 内未完成")

    # ============================================================
    # 项目管理
    # ============================================================

    async def create_book(
        self,
        title: str,
        genre: str = "",
        synopsis: str = "",
        outline_mode: str = "one_to_one",
    ) -> dict:
        """创建新书。返回 {id, title, outline_mode}。"""
        return await self._request(
            "POST",
            "/books",
            {
                "title": title,
                "genre": genre,
                "synopsis": synopsis,
                "outline_mode": outline_mode,
            },
        )

    async def list_books(self) -> list[dict]:
        """列出所有书。返回 [{id, title, genre, ...}]。"""
        return await self._request("GET", "/books")

    # ============================================================
    # 章节
    # ============================================================

    async def list_chapters(self, project_id: int) -> list[dict]:
        """列出项目所有章节。返回 [{id, no, title, words, status, ...}]。"""
        return await self._request("GET", f"/projects/{project_id}/chapters")

    async def get_chapter(self, project_id: int, chapter_id: int) -> dict:
        """获取章节完整内容。返回 {id, title, content, word_count, ...}。"""
        return await self._request("GET", f"/projects/{project_id}/chapters/{chapter_id}")

    async def generate_chapter(
        self,
        project_id: int,
        *,
        chapter_ids: list[int] | None = None,
        start: int | None = None,
        count: int | None = None,
        target_word_count: int = 2500,
        poll: bool = True,
    ) -> dict:
        """生成章节（异步，默认自动轮询到完成）。

        单章: chapter_ids=[28]
        连续: start=3, count=5
        poll=False 时立即返回 task_id，不等待。
        """
        body: dict[str, Any] = {"target_word_count": target_word_count}
        if chapter_ids:
            body["chapter_ids"] = chapter_ids
        elif start is not None and count is not None:
            body["start_chapter_number"] = start
            body["count"] = count
        else:
            raise ValueError("请提供 chapter_ids 或 start+count")

        result = await self._request(
            "POST", f"/projects/{project_id}/chapters/batch-generate", body
        )
        if poll and result.get("task_id"):
            return await self._poll_async(
                result,
                f"/projects/{project_id}/batch-generate/{{task_id}}/status",
            )
        return result

    async def regenerate_chapter(
        self,
        project_id: int,
        chapter_id: int,
        instructions: str = "",
        target_word_count: int | None = None,
    ) -> dict:
        """重写章节（用 Diff Rewrite 润色）。"""
        body: dict[str, Any] = {"instructions": instructions}
        if target_word_count:
            body["target_word_count"] = target_word_count
        return await self._request(
            "POST", f"/projects/{project_id}/chapters/{chapter_id}/regenerate", body
        )

    async def clear_chapter(self, project_id: int, chapter_id: int) -> dict:
        """清空章节内容，回到 draft 状态。"""
        return await self._request(
            "POST", f"/projects/{project_id}/chapters/{chapter_id}/clear"
        )

    # ============================================================
    # 大纲
    # ============================================================

    async def list_outlines(self, project_id: int) -> list[dict]:
        """列出项目大纲。"""
        return await self._request("GET", f"/projects/{project_id}/outlines")

    async def generate_outline(self, project_id: int, poll: bool = True) -> dict:
        """生成大纲（异步，默认自动轮询）。"""
        result = await self._request(
            "POST", f"/projects/{project_id}/outlines/generate-async"
        )
        if poll and result.get("task_id"):
            return await self._poll_async(
                result, f"/projects/{project_id}/outlines/status?task={{task_id}}"
            )
        return result

    async def continue_outline(self, project_id: int, poll: bool = True) -> dict:
        """续写大纲（异步）。"""
        result = await self._request(
            "POST", f"/projects/{project_id}/outlines/continue-async"
        )
        if poll and result.get("task_id"):
            return await self._poll_async(
                result, f"/projects/{project_id}/outlines/status?task={{task_id}}"
            )
        return result

    async def expand_outline(
        self, project_id: int, outline_id: int, poll: bool = True
    ) -> dict:
        """展开大纲（1-N 模式：1卷→多章）。"""
        result = await self._request(
            "POST", f"/projects/{project_id}/outlines/{outline_id}/expand-async"
        )
        if poll and result.get("task_id"):
            return await self._poll_async(
                result, f"/projects/{project_id}/batch-generate/{{task_id}}/status"
            )
        return result

    # ============================================================
    # 任务管理
    # ============================================================

    async def get_active_task(self, project_id: int) -> dict | None:
        """获取当前活跃的异步任务。无任务时返回空 dict。"""
        return await self._request(
            "GET", f"/projects/{project_id}/batch-generate/active"
        )

    async def cancel_task(self, project_id: int, task_id: int) -> dict:
        """取消正在运行的批量任务。"""
        return await self._request(
            "POST", f"/projects/{project_id}/batch-generate/{task_id}/cancel"
        )
