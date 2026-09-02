"""多会话管理（任务 4.5）：memory/sessions/<会话ID>.jsonl 按会话隔离存储完整对话。

与 memory/history.jsonl 的分工：history.jsonl 是"全部历史的平面审计日志"（只有
role/content，不可回放）；会话文件保存**全保真**消息（含 tool_calls / tool_call_id），
是 /resume 的回放数据源——OpenAI 协议要求 role="tool" 消息必须紧跟带 tool_calls 的
assistant 消息，少了配对信息的历史无法重新喂给模型。

load 时做协议修复：若会话在工具调用中途崩溃，末尾会留下"有 tool_calls 却没有
对应 tool 结果"的 assistant 消息，直接回放会被 API 拒绝，补一条占位 tool 结果。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .config import SESSIONS_DIR

# 会话文件轮转（红4）：会话没有"关闭"概念（持续追加），长跑会无界增长。
# 单文件超阈值就把当前 active 文件改名归档，新 append 自动开新文件。
SESSION_MAX_BYTES = int(os.environ.get("EMPEROR_SESSION_MAX_BYTES", str(10 * 1024 * 1024)))
SESSION_MAX_BACKUPS = int(os.environ.get("EMPEROR_SESSION_MAX_BACKUPS", "3"))


class SessionStore:
    """会话的创建、追加（全保真）、加载（含修复）、列表。"""

    def __init__(self, sessions_dir: Path):
        self.dir = sessions_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.titles_path = self.dir / "titles.json"   # G2：会话标题（list_sessions 只扫 *.jsonl，不会误列）
        self._used_ids: set[str] = set()  # 同秒多次 new_session 的进程内撞名防护

    # ---- G2：标题存取（独立 JSON，避免动全保真会话文件） ----
    def _load_titles(self) -> dict:
        if not self.titles_path.exists():
            return {}
        try:
            return json.loads(self.titles_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def set_title(self, session_id: str, title: str) -> None:
        data = self._load_titles()
        data[session_id] = title
        self.titles_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_title(self, session_id: str) -> str:
        return self._load_titles().get(session_id, "")

    # ---- G3：回滚截断（另拟/改旨：文件行数与 history 一一对应，按前缀重写） ----
    def truncate(self, session_id: str, keep: int) -> None:
        path = self._path(session_id)
        if not path.exists():
            return
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        path.write_text("".join(l + "\n" for l in lines[:keep]), encoding="utf-8")

    def new_session(self) -> str:
        """时间戳命名，同秒冲突时加序号。文件懒创建：首次 append 才落盘。

        撞名检查要同时看磁盘和内存：会话文件是懒创建的，仅查磁盘会漏掉
        "同秒内先建了会话但还没写入"的撞车（单测实测抓到过）。
        """
        base = f"{datetime.now():%Y%m%d-%H%M%S}"
        sid, n = base, 0
        while sid in self._used_ids or (self.dir / f"{sid}.jsonl").exists():
            n += 1
            sid = f"{base}-{n}"
        self._used_ids.add(sid)
        return sid

    def _path(self, session_id: str) -> Path:
        # 只取文件名部分，防止 /resume 传入路径穿越
        return self.dir / f"{Path(session_id).name}.jsonl"

    def exists(self, session_id: str) -> bool:
        return self._path(session_id).exists()

    def append(self, session_id: str, message: dict) -> None:
        path = self._path(session_id)
        _rotate_session_if_needed(path)
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "msg": message}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load(self, session_id: str) -> list[dict]:
        """读回全保真消息并做协议修复，可直接作为 messages 喂给模型。"""
        path = self._path(session_id)
        if not path.exists():
            return []
        messages: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line)["msg"])
            except (json.JSONDecodeError, KeyError):
                continue
        return self._repair(messages)

    @staticmethod
    def _repair(messages: list[dict]) -> list[dict]:
        """补齐悬空的 tool_calls（只可能出现在末尾：追加是顺序写入的）。

        会话若停在"assistant 发起工具调用之后、结果回来之前"（如进程崩溃），
        直接回放会违反消息配对协议；给每个缺结果的调用补一条占位 tool 消息。
        """
        answered = {
            m.get("tool_call_id")
            for m in messages
            if m.get("role") == "tool" and m.get("tool_call_id")
        }
        repaired = list(messages)
        last = repaired[-1] if repaired else None
        if last and last.get("role") == "assistant" and last.get("tool_calls"):
            for tc in last["tool_calls"]:
                if tc.get("id") not in answered:
                    repaired.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "（会话中断，该工具调用未完成，请重新发起）",
                    })
        return repaired

    def list_sessions(self) -> list[dict]:
        """按修改时间新→旧列出会话：ID、时间、条数、首条用户消息预览。"""
        sessions = []
        for f in sorted(self.dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
            lines = [l for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
            first_user = ""
            for l in lines:
                try:
                    msg = json.loads(l).get("msg", {})
                except json.JSONDecodeError:
                    continue
                if msg.get("role") == "user":
                    first_user = str(msg.get("content", ""))[:30]
                    break
            # G2：有 LLM 生成的标题优先（偏殿名册"像人话"的关键）
            preview = self.get_title(f.stem) or first_user or "(空会话)"
            sessions.append({
                "id": f.stem,
                "messages": len(lines),
                "mtime": datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M"),
                "preview": preview,
            })
        return sessions

    def render_list(self) -> str:
        items = self.list_sessions()
        if not items:
            return "暂无历史会话。"
        lines = ["历史会话（新→旧，最多显示 15 个）："]
        for s in items[:15]:
            lines.append(f"  {s['id']}  [{s['mtime']}] {s['messages']}条  {s['preview']}")
        lines.append("用 /resume <会话ID> 恢复继续。")
        return "\n".join(lines)


def _rotate_session_if_needed(path: Path) -> None:
    """会话文件轮转（红4）：超阈值把当前 active 文件改名归档。

    会话没有“关闭”概念（一直在追加），所以轮转时机 = 单次 append 之前。
    改法与 hooks 轮转一致：旧文件依次往后挪，最多保留 N 份。
    """
    if not path.exists() or path.stat().st_size < SESSION_MAX_BYTES:
        return
    stem, parent = path.stem, path.parent
    for i in range(SESSION_MAX_BACKUPS, 0, -1):
        src = parent / f"{stem}-{i}.jsonl.bak"
        if i == SESSION_MAX_BACKUPS:
            if src.exists(): src.unlink()
        else:
            dst = parent / f"{stem}-{i+1}.jsonl.bak"
            if src.exists(): src.replace(dst)
    path.replace(parent / f"{stem}-1.jsonl.bak")


SESSIONS = SessionStore(SESSIONS_DIR)
