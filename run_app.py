#!/usr/bin/env python3
"""run_app.py — Emperor Agent 桌面壳（任务 D1）。

一条命令弹出独立窗口：uvicorn 在后台线程伺服 web/，pywebview 占主线程
（它要求主线程跑事件循环）。关窗触发完整清理链：
窗口关闭 → 停 uvicorn → atexit 清 MCP 会话 → 进程退出 → 队友守护线程随之消亡。

用法：python run_app.py（端口可用环境变量 EMPEROR_PORT 覆盖）
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _ensure_env_or_guide() -> None:
    """（F4 已废弃原逻辑）首启引导改由界面内的「模型阁」承担：
    无任何模型配置时，前端自动展开添加表单，用户填完即用，无需理解 .env。"""
    return None

import uvicorn
import webview

from agent_core.console import ensure_utf8_console

HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("EMPEROR_PORT", "8300"))


def _pick_port() -> int:
    """选一个可用端口：优先默认 8300，被占则让 OS 分配随机空闲端口。

    固定端口的代价（实测翻车）：本机常驻软件（如 O+Connect 手机互联）
    抢占 8300 → 服务起不来 → 窗口黑屏；偶尔启动成功也会被干扰断连。
    注意不用 SO_REUSEADDR：Windows 上它允许重复绑定"正在使用"的端口，
    检测会假阳性（实测翻车）；connect 探测才是可靠判据。
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex((HOST, DEFAULT_PORT)) != 0:
            return DEFAULT_PORT  # 连不上 = 没人监听 = 可用
    # 默认口被占：让 OS 从临时端口段挑一个空闲的（bind(0) 的标准用法）
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _port_ready(port: int) -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, port)) == 0


def _serve(port: int):
    """后台线程跑 uvicorn（D1：pywebview 需要主线程，服务只能让位）。"""
    from web.server import app  # 延迟导入：lifespan 里的 MCP 连接在服务启动时才发生

    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
    uvicorn.Server(config).run()


def main() -> None:
    ensure_utf8_console()   # GBK 控制台 print emoji 会炸内核，入口处统一 UTF-8
    _ensure_env_or_guide()
    port = _pick_port()
    if port != DEFAULT_PORT:
        print(f"[Emperor Agent] 默认端口 {DEFAULT_PORT} 被占用（常见于常驻软件如手机互联工具），"
              f"本次改用 {port}")
    thread = threading.Thread(target=_serve, args=(port,), name="emperor-server", daemon=True)
    thread.start()

    # 轮询等端口就绪（最多 30 秒；MCP 连接慢时窗口宁可晚开也不白屏）
    deadline = time.time() + 30
    while not _port_ready(port):
        if time.time() > deadline:
            print("[Emperor Agent] 服务启动超时，请检查 MCP 配置后重试")
            sys.exit(1)
        time.sleep(0.2)

    window = webview.create_window(
        title="Emperor Agent · 金銮殿",
        url=f"http://{HOST}:{port}/",
        width=1280,
        height=860,
        min_size=(720, 520),
    )
    # 关窗即退出（默认行为）；清理链由 uvicorn 停止 + atexit(MCP) + 进程退出共同完成
    webview.start()
    print("[Emperor Agent] 窗口已关闭，进程收队。")


if __name__ == "__main__":
    main()
