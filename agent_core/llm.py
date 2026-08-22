"""LLM 客户端与 OpenAI 协议消息适配。"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.environ["LLM_API_KEY"],
    base_url=os.environ["LLM_BASE_URL"],
)

MODEL = os.environ["LLM_MODEL"]


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
