"""Emperor Agent · Web 服务入口（任务 A1：FastAPI 服务骨架）。

UIPLAN 红线：只监听 127.0.0.1——本 Agent 具备命令执行与文件读写能力，
绝不暴露到局域网。启动：python web/server.py（端口可用环境变量 EMPEROR_PORT 覆盖）。
"""
from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Emperor Agent")


@app.get("/api/health")
async def health():
    return {"ok": True, "app": "Emperor Agent"}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",  # 红线：只绑本机回环，验收必查 netstat
        port=int(os.environ.get("EMPEROR_PORT", "8300")),
        log_level="info",
    )
