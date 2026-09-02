"""LLM 客户端与 OpenAI 协议消息适配（F2：运行时可重建）。

client / MODEL / CONTEXT_WINDOW 是模块级全局，但调用方一律通过
`llm.client` 等属性引用（不可 `from .llm import client`——那会焊死旧对象，
换配置后引用者看不见新 client）。apply_profile() 换配置时原地重建，
所有调用方下一轮自动生效（PLAN Backlog "llm client 运行时重建"转正落地）。

启动顺序：model_profiles.json 的活跃档案优先；没有则用 .env 种子/兜底；
再没有 client=None——call_llm 会发出"未配置模型"的引导错误，界面打开
模型阁填表即可。
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

from openai import OpenAI
from dotenv import load_dotenv

from . import model_profiles
from .config import CONTEXT_WINDOW as _ENV_CONTEXT_WINDOW

load_dotenv()

client: OpenAI | None = None
MODEL: str = ""
CONTEXT_WINDOW: int = _ENV_CONTEXT_WINDOW


def apply_profile(profile: dict | None) -> None:
    """把一个模型档案设为当前（原地重建 client）。profile=None 表示未配置。"""
    global client, MODEL, CONTEXT_WINDOW
    if not profile or not profile.get("base_url") or not profile.get("model"):
        client = None
        MODEL = ""
        return
    # 本地服务（Ollama 等）允许空 key：OpenAI SDK 要求非 None，用占位符
    client = OpenAI(api_key=profile.get("api_key") or "EMPTY",
                    base_url=profile["base_url"])
    MODEL = profile["model"]
    cw = profile.get("context_window")
    CONTEXT_WINDOW = int(cw) if cw else _ENV_CONTEXT_WINDOW


apply_profile(model_profiles.get_active())


def assistant_to_dict(message) -> dict:
    """把 chat.completions 返回的 assistant 消息转成普通 dict 存入 history。

    带工具调用时必须原样保留 tool_calls 字段，下轮请求才能连同
    role="tool" 的结果一起回传（OpenAI 协议要求）。
    """
    entry = {"role": "assistant", "content": message.content}
    if message.tool_calls:
        entry["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in message.tool_calls
        ]
    return entry


def to_tool_call(tc) -> SimpleNamespace:
    """把 OpenAI 的 tool_call 适配成 {id, name, input} 结构，复用原有工具分发逻辑。"""
    return SimpleNamespace(id=tc.id, name=tc.function.name, input=json.loads(tc.function.arguments or "{}"))
