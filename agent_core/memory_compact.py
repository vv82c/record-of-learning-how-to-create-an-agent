"""记忆压缩：history 超过阈值时，把旧消息沉淀进记忆文件，只保留最近一段。

补回 step07 有、step09+ 丢失的能力：
1. compact_history：把旧对话交给 LLM 压缩成三部分：
   - <episode>        今日情景记忆（追加到 memory/YYYY-MM-DD.md）
   - <updated_memory> 更新后的长期记忆 MEMORY.md（全量覆盖）
   - <updated_user>   更新后的用户画像 USER.md（全量覆盖）

2. _append_episode：情景记忆写入（step07 的 MemoryStore.append_episode）。

与 step07 版本的差异：
- 独立成模块，通过参数注入 client / model / memory_store，避免循环导入；
- 切分点强制落在 user 消息边界上，避免截出"孤儿 tool 消息"
  （OpenAI 协议要求 role="tool" 必须紧跟在带 tool_calls 的 assistant 消息之后）；
- 压缩提示词模板从 templates/agent/compact_prompt.md 读取。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .config import COMPACT_PROMPT_PATH

RECENT_MESSAGES = int(os.environ.get("AGENT_MEMORY_RECENT", "10"))
COMPACT_AFTER_MESSAGES = int(os.environ.get("AGENT_MEMORY_COMPACT_AFTER", "18"))


def _extract_tag(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else ""


def _messages_to_text(messages: list[dict]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "?")
        content = json.dumps(msg.get("content"), ensure_ascii=False, default=str)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _append_episode(memory_store, text: str):
    """把情景记忆追加到 memory/YYYY-MM-DD.md。"""
    memory_store.ensure_files()
    path = memory_store.memory_dir / f"{datetime.now():%Y-%m-%d}.md"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n" + text.strip() + "\n")


def _find_split_point(history: list[dict]) -> int | None:
    """返回切分下标 i：old = history[:i]，recent = history[i:]。

    要求 history[i] 是 user 消息，保证 recent 第一条不是孤立的
    tool / assistant(tool_calls) 消息，符合 OpenAI 消息配对规则。
    找不到合适切分点时返回 None（本轮跳过压缩）。
    """
    limit = len(history) - RECENT_MESSAGES
    for i in range(limit, 0, -1):
        if history[i].get("role") == "user":
            return i
    return None


def compact_history(
    history: list[dict],
    client,
    model: str,
    memory_store,
    max_tokens: int = 3000,
) -> list[dict]:
    """history 超过阈值时压缩：旧消息沉淀进记忆文件，只保留最近一段。

    压缩失败时不抛异常，原样返回 history（宁可不压缩，不能中断对话）。
    """
    if len(history) <= COMPACT_AFTER_MESSAGES:
        return history

    split = _find_split_point(history)
    if split is None:
        return history

    old_messages = history[:split]
    recent_messages = history[split:]

    try:
        prompt_template = COMPACT_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[记忆压缩跳过：缺少模板 {COMPACT_PROMPT_PATH}]: {exc}")
        return history

    prompt = prompt_template.format(
        old_conversation=_messages_to_text(old_messages),
        current_memory=memory_store.read_memory(),
        current_user=memory_store.read_user(),
        today_episode=memory_store.read_today_episode(),
        now_hhmm=datetime.now().strftime("%H:%M"),
    )

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": "你是记忆整理员。请严格按要求输出 XML，不要输出额外解释。"},
                {"role": "user", "content": prompt},
            ],
        )
        text = response.choices[0].message.content or ""
    except Exception as exc:
        print(f"[记忆压缩失败，保留完整 history]: {exc}")
        return history

    episode = _extract_tag(text, "episode")
    updated_memory = _extract_tag(text, "updated_memory")
    updated_user = _extract_tag(text, "updated_user")

    if episode:
        _append_episode(memory_store, episode)
    if updated_memory:
        memory_store.write_memory(updated_memory)
    if updated_user:
        memory_store.write_user(updated_user)

    print(f"[记忆已压缩]: old={len(old_messages)} recent={len(recent_messages)}")
    return recent_messages
