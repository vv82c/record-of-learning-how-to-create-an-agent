"""Agent Team：持久队友 + 文件 inbox 消息总线。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .config import INBOX_DIR, TEAM_DIR
from .llm import MODEL, assistant_to_dict, client, to_tool_call

VALID_MSG_TYPES = {
    "message",
    "broadcast",
    "shutdown_request",
    "shutdown_response",
    "plan_approval_response",
}

# 队友可用的工具白名单（任务 4.1）：schema 与执行都走 agent_core.registry。
# 模型只能调用 schema 曝露给它的工具（见 registry），执行前再过一道白名单兜底。
TEAMMATE_TOOL_NAMES = [
    "run_command", "web_fetch", "load_skill", "list_mcp_servers",
    "read_file", "write_file", "glob", "grep",
    "send_message", "read_inbox",
]

RUNTIME_STATUSES = {"idle", "working"}
TERMINAL_STATUSES = {"offline", "shutdown"}


class MessageBus:
    """每个队友一个 JSONL inbox。发送=追加一行，读取=读完后清空。"""

    def __init__(self, inbox_dir: Path):
        self.dir = inbox_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict | None = None) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: invalid msg_type '{msg_type}', valid={sorted(VALID_MSG_TYPES)}"
        msg = {
            "type": msg_type,
            "from": sender,
            "content": content,
            "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        inbox_path = self.dir / f"{to}.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return f"已送达 {to} 的 inbox：{msg_type}"

    def read_inbox(self, name: str) -> list[dict]:
        inbox_path = self.dir / f"{name}.jsonl"
        if not inbox_path.exists():
            return []
        messages = []
        for line in inbox_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                messages.append({
                    "type": "message",
                    "from": "system",
                    "content": f"Error: inbox line parse failed: {e}",
                    "timestamp": time.time(),
                })
        inbox_path.write_text("", encoding="utf-8")
        return messages

    def broadcast(self, sender: str, content: str, teammates: list[str]) -> str:
        count = 0
        for name in teammates:
            if name == sender:
                continue
            self.send(sender, name, content, "broadcast")
            count += 1
        return f"已广播给 {count} 位队友"


BUS = MessageBus(INBOX_DIR)


class TeammateManager:
    """管理一支持久 agent team：名字、角色、状态和各自的线程。"""

    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.config = self._load_config()
        self.threads: dict[str, threading.Thread] = {}
        self.lock = threading.Lock()
        self._mark_stale_members_offline()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return {"team_name": "default", "members": []}

    def _save_config(self):
        self.config_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _mark_stale_members_offline(self):
        """进程重启后，config 还在，但旧线程已经不存在。

        所以启动时把上次遗留的 idle/working 改成 offline，避免误导用户。
        """
        changed = False
        for member in self.config.get("members", []):
            if member.get("status") in RUNTIME_STATUSES:
                member["status"] = "offline"
                changed = True
        if changed:
            self._save_config()

    def _find_member(self, name: str) -> dict | None:
        for member in self.config["members"]:
            if member["name"] == name:
                return member
        return None

    def _set_status(self, name: str, status: str):
        with self.lock:
            member = self._find_member(name)
            if member:
                member["status"] = status
                self._save_config()

    def spawn(self, name: str, role: str, prompt: str) -> str:
        name = name.strip()
        role = role.strip() or "teammate"
        if not name:
            return "Error: name 不能为空"

        with self.lock:
            member = self._find_member(name)
            if member:
                running = self.threads.get(name)
                if running and running.is_alive():
                    BUS.send("lead", name, prompt)
                    member["role"] = role
                    member["status"] = "working"
                    self._save_config()
                    return f"'{name}' 已在队中，已把新差事送入 inbox"
                member["role"] = role
                member["status"] = "working"
            else:
                member = {"name": name, "role": role, "status": "working"}
                self.config["members"].append(member)
            self._save_config()

        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        self.threads[name] = thread
        thread.start()
        return f"已召入/唤回队友 '{name}'（职司：{role}），队友线程已启动"

    def _teammate_loop(self, name: str, role: str, prompt: str):
        system_prompt = (
            f"你是大内团队中的固定队友，名叫{name}，职司是{role}。\n"
            f"当前目录：{Path.cwd()}。\n"
            "你不是一次性小太监，而是 agent team 的持久成员。\n"
            "你可以通过 send_message 给 lead 或其他队友发消息，也可以 read_inbox 读取自己的 inbox。\n"
            "收到差事后尽快办妥；办完用 send_message 向 lead 回禀简短结果，然后等待下一封 inbox。\n"
            "若收到 shutdown_request，可回禀 shutdown_response 后停止。"
        )
        tools = self._teammate_tools()
        messages = [{"role": "user", "content": prompt}]
        has_work = True

        while True:
            inbox = BUS.read_inbox(name)
            for msg in inbox:
                if msg.get("type") == "shutdown_request":
                    BUS.send(name, msg.get("from", "lead"), "准许退下，队友线程即将停止。", "shutdown_response")
                    self._set_status(name, "shutdown")
                    return
                messages.append({
                    "role": "user",
                    "content": "<inbox>\n" + json.dumps(msg, ensure_ascii=False, indent=2) + "\n</inbox>",
                })
                has_work = True

            if not has_work:
                self._set_status(name, "idle")
                time.sleep(1)
                continue

            self._set_status(name, "working")
            for turn in range(20):
                try:
                    msg = client.chat.completions.create(
                        model=MODEL,
                        max_tokens=4000,
                        messages=[{"role": "system", "content": system_prompt}] + messages,
                        tools=tools,
                    ).choices[0].message
                except Exception as e:
                    BUS.send(name, "lead", f"Error: 队友 {name} 调用模型失败：{e}")
                    self._set_status(name, "idle")
                    has_work = False
                    break

                messages.append(assistant_to_dict(msg))

                if not msg.tool_calls:
                    final = msg.content or ""
                    if final.strip():
                        BUS.send(name, "lead", final.strip())
                    print(f"[队友 {name} 空闲]: 本轮 {turn + 1} 次调用后回到 idle")
                    self._set_status(name, "idle")
                    has_work = False
                    break

                for tc in msg.tool_calls:
                    block = to_tool_call(tc)
                    output = self._exec(name, block.name, block.input)
                    print(f"  [队友·{name}·{block.name}]: {str(output)[:160]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(output),
                    })
            else:
                BUS.send(name, "lead", f"队友 {name} 达到本轮 20 次调用上限，已暂停等待下一步指令。")
                self._set_status(name, "idle")
                has_work = False

    def _exec(self, sender: str, tool_name: str, args: dict) -> str:
        # 函数内导入 registry：registry 在模块级导入了 team，模块级互相导入会成环
        from .registry import execute_tool
        if tool_name not in TEAMMATE_TOOL_NAMES:
            return f"Error: unknown teammate tool '{tool_name}'"
        return execute_tool(tool_name, args, sender=sender, prefix=f"队友({sender})·")

    def _teammate_tools(self) -> list[dict]:
        from .registry import get_schemas
        return get_schemas(TEAMMATE_TOOL_NAMES)

    def list_all(self) -> str:
        with self.lock:
            if not self.config["members"]:
                return "暂无队友。"
            lines = [f"Team: {self.config.get('team_name', 'default')}"]
            for member in self.config["members"]:
                status = member["status"]
                note = "（需重新 spawn 才会处理 inbox）" if status == "offline" else ""
                lines.append(f"  - {member['name']}（{member['role']}）：{status}{note}")
            return "\n".join(lines)

    def member_names(self) -> list[str]:
        with self.lock:
            return [m["name"] for m in self.config["members"]]


TEAM = TeammateManager(TEAM_DIR)
