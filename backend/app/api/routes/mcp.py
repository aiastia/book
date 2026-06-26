"""MCP 服务器管理 API"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.mcp_server import McpServer
from app.services.mcp_client_service import McpClientService

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


class McpServerCreate(BaseModel):
    name: str
    url: str
    transport: str = "streamable-http"
    description: str = ""
    api_key: str = ""
    config: Optional[dict] = None


class McpServerUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    transport: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    config: Optional[dict] = None


async def get_current_user_id(request=None):
    """简化：从 request.state 获取 user_id"""
    # 实际在路由中使用 Depends(get_current_user)
    return None


@router.get("/servers")
async def list_servers(db: AsyncSession = Depends(get_db)):
    """列出所有 MCP Server（首次调用时预置 Tavily Search）。"""
    # 预置 Tavily Search（默认禁用）
    existing = (await db.execute(
        select(McpServer).where(McpServer.name == "Tavily Search", McpServer.user_id == 1)
    )).scalar_one_or_none()
    if not existing:
        db.add(McpServer(
            user_id=1, name="Tavily Search",
            url="https://api.tavily.com/mcp",
            transport="streamable-http",
            description="网络搜索工具，AI 写作时可查询实时信息、百科资料。需配置 API Key（https://tavily.com）",
            enabled=False,
            config={"api_key": ""},
        ))
        await db.commit()

    result = await db.execute(select(McpServer))
    return [s.to_dict() for s in result.scalars().all()]


@router.post("/servers")
async def create_server(req: McpServerCreate, db: AsyncSession = Depends(get_db)):
    server = McpServer(
        user_id=1,  # 临时
        name=req.name, url=req.url, transport=req.transport,
        description=req.description,
        config={"api_key": req.api_key, **(req.config or {})},
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server.to_dict()


@router.put("/servers/{server_id}")
async def update_server(server_id: int, req: McpServerUpdate, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "MCP Server 不存在")
    if req.name is not None: s.name = req.name
    if req.url is not None: s.url = req.url
    if req.transport is not None: s.transport = req.transport
    if req.enabled is not None: s.enabled = req.enabled
    if req.description is not None: s.description = req.description
    if req.api_key is not None: s.config = {**(s.config or {}), "api_key": req.api_key}
    if req.config is not None: s.config = {**(s.config or {}), **req.config}
    await db.commit()
    return s.to_dict()


@router.delete("/servers/{server_id}")
async def delete_server(server_id: int, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "MCP Server 不存在")
    await db.delete(s)
    await db.commit()
    return {"ok": True}


@router.post("/servers/{server_id}/discover")
async def discover_tools(server_id: int, db: AsyncSession = Depends(get_db)):
    """发现 MCP Server 的工具列表。"""
    s = (await db.execute(select(McpServer).where(McpServer.id == server_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "MCP Server 不存在")
    service = McpClientService(db, user_id=s.user_id)
    tools = await service._discover_tools(s.to_dict())
    return {"tools": tools, "count": len(tools)}
