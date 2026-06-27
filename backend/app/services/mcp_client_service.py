"""MCP 客户端服务：连接外部 MCP Server，获取工具列表，执行工具调用。"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import McpServer

logger = logging.getLogger(__name__)


class McpClientService:
    """MCP 客户端：管理 MCP Server 连接和工具调用。"""

    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id

    async def list_enabled_servers(self) -> list:
        """列出启用的 MCP Server。"""
        result = await self.db.execute(
            select(McpServer).where(
                McpServer.user_id == self.user_id,
                McpServer.enabled == True,
            )
        )
        return [s.to_dict() for s in result.scalars().all()]

    async def fetch_tools(self) -> list[dict]:
        """从所有启用的 MCP Server 获取工具列表（OpenAI function calling 格式）。"""
        servers = await self.list_enabled_servers()
        all_tools = []
        for s in servers:
            try:
                tools = await self._discover_tools(s)
                for tool in tools:
                    tool["_mcp_server"] = s["id"]
                    all_tools.append(tool)
            except Exception as e:
                logger.warning(f"[MCP] 获取工具失败 server={s['name']}: {e}")
        return all_tools

    async def execute_tool(self, server_id: int, tool_name: str, arguments: dict) -> str:
        """在指定 MCP Server 上执行工具。"""
        server = (
            await self.db.execute(
                select(McpServer).where(
                    McpServer.id == server_id, McpServer.user_id == self.user_id
                )
            )
        ).scalar_one_or_none()
        if not server:
            return json.dumps({"error": "MCP Server 不存在"})
        try:
            return await self._call_tool(server, tool_name, arguments)
        except Exception as e:
            logger.warning(f"[MCP] 执行工具失败 {tool_name}: {e}")
            return json.dumps({"error": str(e)})

    async def _discover_tools(self, server_dict: dict) -> list[dict]:
        """从 MCP Server 发现工具列表。"""
        import aiohttp

        url = server_dict["url"].rstrip("/")
        api_key = (server_dict.get("config", {}) or {}).get("api_key", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-Api-Key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            # MCP streamable-http: POST /mcp with method=tools/list
            payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
            try:
                async with session.post(
                    f"{url}/mcp" if "/mcp" not in url else url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    tools = data.get("result", {}).get("tools", [])
            except Exception:
                # 回退：直接 GET /tools
                try:
                    async with session.get(
                        f"{url}/tools",
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            tools = data if isinstance(data, list) else data.get("tools", [])
                        else:
                            return []
                except Exception:
                    return []

        # 转换为 OpenAI function calling 格式
        openai_tools = []
        for tool in tools:
            name = tool.get("name", "")
            desc = tool.get("description", "")
            schema = tool.get("inputSchema", tool.get("parameters", {}))
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": f"mcp_{name}",
                        "description": f"[MCP:{server_dict['name']}] {desc}",
                        "parameters": {
                            "type": "object",
                            "properties": schema.get("properties", {}),
                            "required": schema.get("required", []),
                        }
                        if schema.get("properties")
                        else {"type": "object", "properties": {}},
                    },
                }
            )
        return openai_tools

    async def _call_tool(self, server: McpServer, tool_name: str, arguments: dict) -> str:
        """调用 MCP 工具。"""
        import aiohttp

        url = server.url.rstrip("/")
        api_key = (server.config or {}).get("api_key", "")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-Api-Key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"

        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            async with session.post(
                f"{url}/mcp" if "/mcp" not in url else url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
            ) as resp:
                data = await resp.json()
                result = data.get("result", {})
                content = result.get("content", [])
                if isinstance(content, list):
                    texts = [c.get("text", "") for c in content if isinstance(c, dict)]
                    return "\n".join(texts) if texts else json.dumps(result)
                return json.dumps(result, ensure_ascii=False)
