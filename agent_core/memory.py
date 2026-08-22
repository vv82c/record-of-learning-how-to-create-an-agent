"""记忆存储：长期记忆 MEMORY.md、用户画像 USER.md、对话历史 history.jsonl、每日情景记忆。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import MEMORY_DIR, TEMPLATES_DIR


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return str(value)


class MemoryStore:
    def __init__(self, memory_dir: Path, templates_dir: Path):
        self.memory_dir = memory_dir
        self.memory_file = memory_dir / "MEMORY.md"
        self.history_file = memory_dir / "history.jsonl"
        self.user_file = templates_dir / "USER.md"

    def ensure_files(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            self.memory_file.write_text("# Long-term Memory\n\n", encoding="utf-8")
        if not self.user_file.exists():
            self.user_file.write_text("# User Profile\n\n", encoding="utf-8")
        if not self.history_file.exists():
            self.history_file.touch()

    def append_history(self, message: dict):
        self.ensure_files()
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "role": message.get("role"),
            "content": _json_safe(message.get("content")),
        }
        with self.history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_memory(self) -> str:
        self.ensure_files()
        return self.memory_file.read_text(encoding="utf-8")

    def write_memory(self, text: str):
        self.ensure_files()
        self.memory_file.write_text(text.strip() + "\n", encoding="utf-8")

    def read_user(self) -> str:
        self.ensure_files()
        return self.user_file.read_text(encoding="utf-8")

    def write_user(self, text: str):
        self.ensure_files()
        self.user_file.write_text(text.strip() + "\n", encoding="utf-8")

    def read_today_episode(self) -> str:
        self.ensure_files()
        path = self.memory_dir / f"{datetime.now():%Y-%m-%d}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""


MEMORY = MemoryStore(MEMORY_DIR, TEMPLATES_DIR)
