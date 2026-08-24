"""Emperor Agent · Web 服务入口。

- 任务 A1：服务骨架与红线（只绑 127.0.0.1——本 Agent 能执行命令，绝不暴露局域网）。
- 任务 A3：WebSocket 事件流 /ws——SessionRunner 内核事件全量转发；
  hook ask 确认从阻塞 input() 改为"事件 + 等待回执"，
  **超时默认驳回（fail-closed）**，语义与终端版一致（终端非交互时同样默认拒绝）。

客户端 → 服务端消息：
  {"type": "send", "text": "..."}       发起一轮对话（同一连接同时只办一件差事）
  {"type": "confirm", "approved": bool} 回应 hook_ask（对应 UI 的"准奏/驳回"）
  {"type": "ping"}                       心跳
服务端 → 客户端事件：SessionRunner 的全部事件（见 agent_core/runner.py）
  另加 idle（本轮办完，可继续传旨）与 pong。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# python web/server.py 时导入根是 web/，自举加上项目根（打包后任意目录可启动）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from agent_core import todos as todos_mod
from agent_core.config import MCP_CONFIG_PATH, PERSONA_DIR, SUBAGENT_LOG_DIR
from agent_core.mcp_client import connect_all, list_mcp_servers
from agent_core.memory import MEMORY
from agent_core.runner import SessionRunner
from agent_core.sessions import SESSIONS
from agent_core.team import TEAM

STATIC_DIR = Path(__file__).resolve().parent / "static"
# ask 等待回执的超时（秒）：超时按驳回处理；测试时可调小
ASK_TIMEOUT = float(os.environ.get("EMPEROR_ASK_TIMEOUT", "120"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_all(MCP_CONFIG_PATH)  # 与终端入口一致：启动即连接 MCP Server
    yield


app = FastAPI(title="Emperor Agent", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "app": "Emperor Agent"}


# ═══════════ C2：面板数据端点（全部只读，操作走 ws 消息） ═══════════
@app.get("/api/sessions")
async def api_sessions():
    return {"sessions": SESSIONS.list_sessions()}


@app.get("/api/memory")
async def api_memory():
    return {"memory": MEMORY.read_memory(), "user": MEMORY.read_user()}


@app.get("/api/personas")
async def api_personas():
    return {"personas": sorted(p.stem for p in PERSONA_DIR.glob("*.md"))}


@app.get("/api/team")
async def api_team():
    return {"team": TEAM.list_all()}


@app.get("/api/mcp")
async def api_mcp():
    # list_mcp_servers 的文本格式（"## server\n- `tool`..."）正好适合面板展示
    return {"mcp": list_mcp_servers()}


@app.get("/api/subagent_logs")
async def api_subagent_logs(limit: int = 5):
    """最近的子代理派遣日志（C3）：文件名 + outcome + 失败统计 + 任务摘要。

    每个文件行数很少（start + N·tool + end），直接全读再截断，无需分页。
    """
    files = sorted(SUBAGENT_LOG_DIR.glob("*.jsonl"), reverse=True) if SUBAGENT_LOG_DIR.exists() else []
    logs = []
    for f in files[:limit]:
        events = []
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    events.append(json.loads(line))
        except (OSError, json.JSONDecodeError):
            continue
        start = next((e for e in events if e.get("event") == "start"), {})
        end = next((e for e in reversed(events) if e.get("event") == "end"), {})
        tool_events = [e for e in events if e.get("event") == "tool"]
        logs.append({
            "file": f.name,
            "agent_type": start.get("agent_type", "?"),
            "task": (start.get("task") or "")[:60],
            "outcome": end.get("outcome", "unknown"),
            "turns": end.get("turns_used", 0),
            "ok": end.get("ok", len([e for e in tool_events if e.get("ok")])),
            "fail": end.get("fail", len([e for e in tool_events if not e.get("ok")])),
            "summary": (end.get("summary") or "")[:150],
        })
    return {"logs": logs}


class WSConfirmer:
    """hook ask 的 ws 桥（任务 A3）。

    runner 线程调用 __call__ 时阻塞等待浏览器的 confirm 回执；
    dispatch_tool 在调用前已发出 hook_ask 事件，这里只负责"等"。
    超时或异常一律返回 False（驳回）——fail-closed 语义与终端版对齐。
    注意：超时与显式驳回在 deny 文案里统一为"用户未确认高敏感操作"。
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, ask_timeout: float):
        self._loop = loop
        self._timeout = ask_timeout
        self._future: asyncio.Future | None = None

    def __call__(self, decision) -> bool:
        wrapper = asyncio.run_coroutine_threadsafe(self._wait(), self._loop)
        try:
            return wrapper.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError:
            fut = self._future
            if fut is not None and not fut.done():
                self._loop.call_soon_threadsafe(fut.cancel)
            return False
        except Exception:
            return False

    async def _wait(self) -> bool:
        self._future = self._loop.create_future()
        return await self._future

    def resolve(self, approved: bool) -> None:
        fut = self._future
        if fut is not None and not fut.done():
            fut.set_result(approved)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    loop = asyncio.get_running_loop()
    out_queue: asyncio.Queue = asyncio.Queue()

    async def pump() -> None:
        """唯一的写者：所有出站消息都经队列串行发送，避免并发写 interleaving。"""
        while True:
            event = await out_queue.get()
            await websocket.send_text(json.dumps(event, ensure_ascii=False))

    def on_event(event: dict) -> None:
        """runner 线程 → 事件循环：线程安全地入队。"""
        loop.call_soon_threadsafe(out_queue.put_nowait, event)

    confirmer = WSConfirmer(loop, ASK_TIMEOUT)
    runner = SessionRunner(on_event=on_event, confirmer=confirmer)
    busy = threading.Event()  # 同一连接同时只办一件差事

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                out_queue.put_nowait({"type": "error", "message": f"无法解析的消息：{raw[:100]}"})
                continue

            kind = msg.get("type")
            if kind == "ping":
                out_queue.put_nowait({"type": "pong"})
            elif kind == "confirm":
                confirmer.resolve(bool(msg.get("approved")))
            elif kind == "stop":
                if busy.is_set():
                    runner.request_stop()   # B3 请旨叫停：在途流断流，工具批后收束
            # ---- C2：会话与人格操作（UI 面板的动作入口） ----
            elif kind == "new_session":
                if not busy.is_set():
                    sid = runner.new_session()
                    out_queue.put_nowait({"type": "session", "id": sid, "fresh": True})
                    out_queue.put_nowait({"type": "todos", "todos": todos_mod.TODOS})
            elif kind == "resume":
                if not busy.is_set():
                    target = str(msg.get("id", ""))
                    if SESSIONS.exists(target):
                        count = runner.resume(target)
                        out_queue.put_nowait({"type": "session", "id": target,
                                              "resumed": True, "messages": count})
                    else:
                        out_queue.put_nowait({"type": "error", "message": f"会话不存在：{target}"})
            elif kind == "persona":
                target = str(msg.get("name", ""))
                available = sorted(p.stem for p in PERSONA_DIR.glob("*.md"))
                if target in available:
                    runner.switch_persona(target)
                    out_queue.put_nowait({"type": "persona", "name": target})
                else:
                    out_queue.put_nowait({"type": "error", "message": f"未知人格：{target}"})
            elif kind == "send":
                if busy.is_set():
                    out_queue.put_nowait({"type": "error", "message": "上一条传旨仍在办理中，请稍候"})
                    continue
                busy.set()
                text = str(msg.get("text", ""))
                out_queue.put_nowait({"type": "user_echo", "text": text})

                def work() -> None:
                    try:
                        runner.send(text)
                    except Exception as exc:  # 内核异常不能拖垮连接
                        on_event({"type": "error", "message": f"[内核异常] {type(exc).__name__}: {exc}"})
                    finally:
                        busy.clear()
                        on_event({"type": "idle"})

                threading.Thread(target=work, daemon=True, name="emperor-send").start()
            else:
                out_queue.put_nowait({"type": "error", "message": f"未知消息类型：{kind}"})
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()


# 静态目录挂到根（html=True 时 "/" 自动伺服 index.html）。
# 注意必须在所有装饰器路由（含上面的 /ws）之后挂载——Starlette 按注册顺序匹配。
# B1 视觉验收抓过坑：只给 "/" 加 FileResponse 而 style.css 404，页面裸奔只剩内联 SVG。
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",  # 红线：只绑本机回环，验收必查 netstat
        port=int(os.environ.get("EMPEROR_PORT", "8300")),
        log_level="info",
    )
