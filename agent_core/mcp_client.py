"""MCP 外部工具协议：连接 stdio MCP Server，把外部工具注册进动态工具表。

注意：MCP_CLIENTS / MCP_TOOL_MAP 是模块级注册表，
connect_all() 会填充它们，list_mcp_servers / build_tool_schemas 都从这里读取。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _mcp_tool_name(server_name: str, mcp_name: str) -> str:
    """把 MCP 原始工具名转换成 OpenAI function calling 可用的 tool name。"""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", mcp_name)
    return f"mcp_{server_name}_{sanitized}"


def _result_to_text(result) -> str:
    """把 MCP CallToolResult 压平成普通文本，方便塞回 role="tool" 消息。"""
    parts = []
    for block in result.content:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        if data.get("type") == "text":
            parts.append(data.get("text", ""))
        else:
            parts.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(parts) if parts else "(empty MCP result)"


class MCPClient:
    """教学版同步 MCP 客户端：每次调用临时启动一次 stdio 会话。"""

    def __init__(self, name: str, params: StdioServerParameters):
        self.name = name
        self.params = params
        self._tools: list | None = None

    async def _alist_tools(self) -> list:
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return list(result.tools)

    async def _acall_tool(self, name: str, arguments: dict[str, Any] | None) -> str:
        async with stdio_client(self.params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments or {})
                return _result_to_text(result)

    def list_tools(self) -> list:
        if self._tools is None:
            self._tools = asyncio.run(self._alist_tools())
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        return asyncio.run(self._acall_tool(name, arguments))

    def stop(self) -> None:
        pass


class MCPConfig:
    """读取项目根目录 mcp_servers.json。"""

    def __init__(self, path: Path):
        self.path = path
        self.servers: dict[str, dict[str, Any]] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.servers = data.get("servers", {})

    def get_params(self, name: str) -> StdioServerParameters | None:
        cfg = self.servers.get(name, {})
        if not cfg.get("enabled", True):
            return None
        command = cfg.get("command")
        if not command:
            return None
        args = cfg.get("args", [])
        env = cfg.get("env")
        if env:
            env = {**os.environ, **env}
        return StdioServerParameters(command=command, args=args, env=env)


def load_mcp_clients(registry: dict, config_path: Path) -> dict[str, MCPClient]:
    """根据配置连接 MCP Server，并把外部工具注册进动态工具表。"""
    config = MCPConfig(config_path)
    clients: dict[str, MCPClient] = {}
    for name in sorted(config.servers.keys()):
        params = config.get_params(name)
        if params is None:
            continue
        try:
            mcp_client = MCPClient(name, params)
            tools = mcp_client.list_tools()
            for tool in tools:
                tool_name = _mcp_tool_name(name, tool.name)
                registry[tool_name] = (mcp_client, tool)
            clients[name] = mcp_client
            print(f"[MCP] 已连接 '{name}'，提供 {len(tools)} 个工具")
        except Exception as exc:
            print(f"[warning] MCP server '{name}' 启动失败：{exc}")
    return clients


MCP_CLIENTS: dict[str, MCPClient] = {}
MCP_TOOL_MAP: dict[str, tuple[MCPClient, Any]] = {}


def connect_all(config_path: Path) -> dict[str, MCPClient]:
    """连接所有配置的 MCP Server，并更新模块级注册表。"""
    global MCP_CLIENTS
    MCP_CLIENTS = load_mcp_clients(MCP_TOOL_MAP, config_path)
    return MCP_CLIENTS


def list_mcp_servers(server: str | None = None) -> str:
    names = [server] if server else sorted(MCP_CLIENTS.keys())
    if not names:
        return "当前没有连接任何 MCP Server。"
    lines = []
    for name in names:
        client = MCP_CLIENTS.get(name)
        if client is None:
            lines.append(f"## {name}\n未连接。")
            continue
        try:
            tools = client.list_tools()
        except Exception as exc:
            lines.append(f"## {name}\n拉取工具列表失败：{exc}")
            continue
        lines.append(f"## {name}")
        for tool in tools:
            registry_name = _mcp_tool_name(name, tool.name)
            desc = getattr(tool, "description", None) or "(no description)"
            lines.append(f"- `{registry_name}` ({tool.name}): {desc}")
    return "\n".join(lines)


def build_tool_schemas(base_tools: list[dict]) -> list[dict]:
    schemas = list(base_tools)
    for tool_name, (mcp_client, tool) in MCP_TOOL_MAP.items():
        # mcp 1.x 的 Tool 字段别名是 inputSchema，2.0.0 起是 input_schema，两者都兼容。
        # （3.1 验证时发现：不配置任何 MCP server 时这段代码根本不执行，
        #   旧写法 tool.inputSchema 在 mcp 2.0.0 下一旦真用到就 AttributeError。）
        input_schema = (
            getattr(tool, "input_schema", None)
            or getattr(tool, "inputSchema", None)
            or {"type": "object", "properties": {}}
        )
        schemas.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": getattr(tool, "description", f"MCP tool '{tool.name}'") or f"MCP tool '{tool.name}'",
                "parameters": input_schema,
            },
        })
    return schemas
