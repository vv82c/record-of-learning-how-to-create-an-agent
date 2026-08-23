"""MCP 外部工具协议：连接 stdio MCP Server，把外部工具注册进动态工具表。

注意：MCP_CLIENTS / MCP_TOOL_MAP 是模块级注册表，
connect_all() 会填充它们，list_mcp_servers / build_tool_schemas 都从这里读取。
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import threading
from contextlib import AsyncExitStack
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


class _BackgroundLoop:
    """专职后台事件循环：MCP 会话是 async 的，而 Agent 是同步多线程代码。

    长连接会话必须活在一个不会退出的事件循环里——旧的 `asyncio.run()` 每次
    调用都会新建再销毁循环，会话随之中断，于是只好每次冷启动子进程。
    现在会话挂在常驻循环上；同步侧用 run_coroutine_threadsafe 提交协程并等结果。
    """

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="mcp-bg-loop", daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro, timeout: float):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


_BACKGROUND_LOOP: _BackgroundLoop | None = None
_BACKGROUND_LOOP_LOCK = threading.Lock()


def _get_background_loop() -> _BackgroundLoop:
    global _BACKGROUND_LOOP
    with _BACKGROUND_LOOP_LOCK:
        if _BACKGROUND_LOOP is None:
            _BACKGROUND_LOOP = _BackgroundLoop()
        return _BACKGROUND_LOOP


class MCPClient:
    """长连接 MCP 客户端（任务 4.3）：会话懒建立、跨调用复用、断线自动重连。

    旧版每次 list_tools / call_tool 都要"spawn 子进程 → initialize → 调用 → 关闭"。
    长连接版把会话挂在后台事件循环上，子进程只在首次（或断线重连）时启动一次。
    """

    def __init__(self, name: str, params: StdioServerParameters):
        self.name = name
        self.params = params
        self._tools: list | None = None
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._lock = threading.Lock()  # 串行化"首次建立"与"断线重建"，避免双开进程

    # ---- 会话生命周期（以下两个协程运行在后台循环里）----
    async def _open(self):
        stack = AsyncExitStack()
        read, write = await stack.enter_async_context(stdio_client(self.params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._exit_stack = stack
        self._session = session

    async def _close(self):
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None

    def _ensure_session(self) -> None:
        loop = _get_background_loop()
        with self._lock:
            if self._session is not None:
                return
            loop.submit(self._open(), timeout=30)

    def _drop_session(self) -> None:
        loop = _get_background_loop()
        with self._lock:
            if self._exit_stack is not None:
                try:
                    loop.submit(self._close(), timeout=10)
                except Exception:
                    pass  # 进程已死时优雅关闭失败是预期内的，直接弃用
            self._session = None
            self._exit_stack = None
            self._tools = None  # 重连后工具清单可能变化，清缓存重新拉取

    # ---- 对外接口（签名与旧版一致）----
    def list_tools(self) -> list:
        if self._tools is not None:
            return list(self._tools)
        self._ensure_session()
        try:
            result = _get_background_loop().submit(self._session.list_tools(), timeout=30)
        except Exception:
            self._drop_session()
            raise
        self._tools = list(result.tools)
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        self._ensure_session()
        try:
            result = _get_background_loop().submit(
                self._session.call_tool(name, arguments or {}), timeout=120,
            )
        except Exception:
            # 会话大概率已坏：丢弃，下次调用自动重建（懒重连，避免这里盲目重试）
            self._drop_session()
            raise
        return _result_to_text(result)

    def stop(self) -> None:
        self._drop_session()


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


def _cleanup_clients() -> None:
    """进程退出前关闭长连接会话，避免 server 子进程残留。"""
    for client in MCP_CLIENTS.values():
        try:
            client.stop()
        except Exception:
            pass


atexit.register(_cleanup_clients)


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
