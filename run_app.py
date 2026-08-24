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

import uvicorn
import webview

HOST, PORT = "127.0.0.1", int(os.environ.get("EMPEROR_PORT", "8300"))


def _port_ready() -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _serve():
    """后台线程跑 uvicorn（D1：pywebview 需要主线程，服务只能让位）。"""
    from web.server import app  # 延迟导入：lifespan 里的 MCP 连接在服务启动时才发生

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
    uvicorn.Server(config).run()


def main() -> None:
    thread = threading.Thread(target=_serve, name="emperor-server", daemon=True)
    thread.start()

    # 轮询等端口就绪（最多 30 秒；MCP 连接慢时窗口宁可晚开也不白屏）
    deadline = time.time() + 30
    while not _port_ready():
        if time.time() > deadline:
            print("[Emperor Agent] 服务启动超时，请检查 MCP 配置后重试")
            sys.exit(1)
        time.sleep(0.2)

    window = webview.create_window(
        title="Emperor Agent · 金銮殿",
        url=f"http://{HOST}:{PORT}/",
        width=1280,
        height=860,
        min_size=(720, 520),
    )
    # 关窗即退出（默认行为）；清理链由 uvicorn 停止 + atexit(MCP) + 进程退出共同完成
    webview.start()
    print("[Emperor Agent] 窗口已关闭，进程收队。")


if __name__ == "__main__":
    main()
