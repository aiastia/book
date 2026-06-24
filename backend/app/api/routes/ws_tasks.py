"""WebSocket 任务推送端点。

通过 WebSocket 实时推送后台任务状态变更，替代前端 HTTP 轮询。
支持无 TLS 的内网环境（ws:// 协议）。

连接：ws://host:8000/ws/tasks?token={jwt_token}
消息格式：JSON { "type": "task_update", "task": {...} }
心跳：服务端每 30 秒发送 {"type":"ping"}，客户端需回复 {"type":"pong"}
"""
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.core.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()


class TaskConnectionManager:
    """WebSocket 连接池管理器。

    按 user_id 管理连接，同一用户可有多个连接（多设备/多标签页）。
    线程安全（单线程 asyncio 天然安全）。
    """

    def __init__(self):
        # user_id -> set[WebSocket]
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)
        logger.debug(f"[ws] 用户 {user_id} 已连接（当前 {len(self._connections[user_id])} 个连接）")

    def disconnect(self, user_id: int, ws: WebSocket):
        if user_id in self._connections:
            self._connections[user_id].discard(ws)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.debug(f"[ws] 用户 {user_id} 已断开")

    async def broadcast_to_user(self, user_id: int, message: dict):
        """向指定用户的所有连接广播消息。"""
        if user_id not in self._connections:
            return
        dead = set()
        payload = json.dumps(message, ensure_ascii=False)
        for ws in self._connections[user_id]:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        # 清理死连接
        for ws in dead:
            self.disconnect(user_id, ws)

    def is_connected(self, user_id: int) -> bool:
        return user_id in self._connections and len(self._connections[user_id]) > 0


# 全局单例
task_ws_manager = TaskConnectionManager()


@router.websocket("/ws/tasks")
async def ws_tasks(ws: WebSocket, token: str = Query(None)):
    """WebSocket 端点：实时接收任务状态推送。

    认证通过 URL query parameter 传递 JWT token。
    """
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return

    # 验证 JWT
    try:
        payload = verify_token(token)
        user_id = payload.get("user_id")
        if not user_id:
            await ws.close(code=4003, reason="Invalid token: missing user_id")
            return
    except Exception:
        await ws.close(code=4003, reason="Invalid or expired token")
        return

    await task_ws_manager.connect(user_id, ws)

    try:
        # 心跳循环：等待客户端消息（pong）或超时
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                # 客户端回复 pong
                msg = json.loads(data)
                if msg.get("type") == "pong":
                    continue
            except asyncio.TimeoutError:
                # 30 秒无消息，发送 ping 保持连接
                try:
                    await ws.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        task_ws_manager.disconnect(user_id, ws)


# ===== 供其他模块调用的广播函数 =====

async def broadcast_task_update(user_id: int, task_data: dict):
    """广播任务状态更新给指定用户。

    由 TaskProgressTracker.update/complete/fail 调用。
    """
    await task_ws_manager.broadcast_to_user(user_id, {
        "type": "task_update",
        "task": task_data,
    })
