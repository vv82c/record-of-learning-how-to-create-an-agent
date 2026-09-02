"""SessionRunner：对话内核驱动器（任务 A2）——把终端 REPL 的主循环抽成可编程调用。

设计要点：
- **双入口共存**：终端 main.py 与 Web 服务（A3 起）驱动同一个 runner，
  工具行为、Hook 链、记忆、压缩、Stop 门禁完全一致；
- **事件流**：内核运行期间通过 on_event(dict) 回调发出 token / tool_start / tool_end /
  todos / hook_ask / hook_decision / subagent_* / retry / error / done / session 等事件。
  终端订阅者只打印对话流相关事件（内层模块已有自己的打印），WebSocket 订阅者全量转发；
- **confirmer 注入**：HookDecision "ask" 的确认动作由构造方提供——终端版传
  hooks.confirm_hook_decision（input() 阻塞），UI 版传"圣旨弹窗"等待（A3）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from openai import APIConnectionError, InternalServerError, RateLimitError

from . import memory_compact, todos as todos_mod
from .config import PERSONA_DIR
from .hooks import HOOKS, HookDecision, confirm_hook_decision
from .llm import MODEL, assistant_to_dict, client, to_tool_call
from .mcp_client import build_tool_schemas
from .memory import MEMORY
from .memory_rag import MEMORY_RAG
from .registry import execute_tool as registry_execute_tool
from .registry import get_schemas
from .sessions import SESSIONS
from .skills import SKILL_LOADER
from .subagent import run_subagent

DEFAULT_PERSONA = "taijian"


# ============== 人格模板（自 main.py 迁入，属内核的提示词装配层） ==============
def load_persona(active_persona: str) -> str:
    """读取人格模板。缺失时回退默认人格，绝不让会话因缺文件而崩溃。"""
    name = Path(active_persona).name
    path = PERSONA_DIR / f"{name}.md"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    fallback = PERSONA_DIR / f"{DEFAULT_PERSONA}.md"
    if fallback.exists():
        return f"(未找到人格 '{name}'，已回退默认人格)\n\n" + fallback.read_text(encoding="utf-8").strip()
    return "你是一个乐于助人的中文智能助手。"


def build_system_prompt(query: str = "", persona: str = DEFAULT_PERSONA) -> str:
    memory = MEMORY_RAG.render_for_prompt(query)
    user_profile = MEMORY.read_user()
    today_episode = MEMORY.read_today_episode()
    return f"""
{load_persona(persona)}

【行事规矩】
1. 用户交办的任务需要多个步骤才能办妥时，先调用 update_todos 工具，
   把整件任务拆成一份清晰的 todolist（每条一句话，按顺序执行）。
2. 拆完计划后，按列表顺序一步步执行：
   - 开始某一步前，把那一步的 status 改为 in_progress（同一时间只许一项 in_progress）。
   - 该步完成后，立即把它改为 completed，再开始下一项。
3. 简单的一句话问答（无需多步骤）不必生成 todolist，直接回答即可。
4. 遇到不熟悉的专题，请先调用 load_skill 工具加载对应知识，再继续。
5. 遇到细节繁多但与主线对话无关的任务（如抓多个网页、批量跑命令、查找文件内容、
   探索性搜索），应**派遣子代理**（dispatch_subagent）去办，主上下文只听汇报即可。
6. 若多件任务互不依赖，可在同一次回复中同时派遣多个子代理，并发执行节省时间。
7. 若用户交办的是长期项目、需要固定角色反复协作，或希望多人互相沟通，
   应组建 agent team：用 spawn_teammate 召入固定队友，再用 send_message / broadcast 分派后续任务。
8. 区分两种调度：
   - dispatch_subagent：临时派遣，办完即散，只回传总结。
   - spawn_teammate：固定班底，有名字、角色、状态和 inbox，可持续协作。
9. 回复使用 Markdown 结构化排版，便于界面渲染与阅读：分节用 ## 标题，要点用列表，
   命令与代码放入 ``` 围栏代码块（标注语言），关键结论加粗；一两句话的简短寒暄不必刻意排版。

【子代理身份选择】
优先选择权限最窄、职司最贴合的身份：
- xiaohuangmen（通传小黄门）：轻量只读，适合短命令、快速确认、跑腿探路。
- sili_suitang（司礼监随堂小太监）：只读文书，适合阅读代码、整理提纲、归纳结论。
- dongchang_tanshi（东厂探事小太监）：只读查访，适合抓网页、查资料、探索性搜索。
- shangbao_dianbu（尚宝监典簿小太监）：只读核验，适合盘点文件、校对清单、检查遗漏。
- neiguan_yingzao（内官监营造小太监）：可读写可执行，适合修改文件、搭建工程、落地实现。

【Agent Team 固定班底】
- spawn_teammate：召入一个有名字和职司的固定队友，队友在独立线程中工作。
- list_teammates：查看队友状态。
- send_message：给某位队友发 inbox 消息。
- read_inbox：读取自己（lead）的 inbox，查看队友回禀。
- broadcast：向所有队友广播消息。
- 队友状态含义：
  - working / idle：本进程里线程还活着。
  - offline：config 里有这个队友，但本进程没有对应线程；需要先 spawn_teammate 唤回，才能继续处理 inbox。
  - shutdown：队友已主动退出。
- 固定队友适合持续协作；一次性探索仍优先派 dispatch_subagent。

【长期记忆 MEMORY.md】
{memory}

【用户画像 USER.md】
{user_profile}

【今日情景记忆】
{today_episode or "(今天还没有压缩出的情景记忆)"}

当前可用技能：
{SKILL_LOADER.get_descriptions()}

【MCP 外部工具】
- 以 `mcp_` 开头的工具来自外部 MCP Server。
- 工具名格式：`mcp_{{server_name}}_{{tool_name}}`。
- 不确定时可调用 `list_mcp_servers` 查看已连接 server 及其工具。

【工具执行约定】
1. 用户要求写文件、读文件、执行命令、查看目录、调用 MCP 或更新计划时，优先发起对应工具调用；写文件用 write_file，读文件用 read_file，执行命令用 run_command。
2. 创建或覆盖本地文件必须调用 write_file，不要用 run_command 拼命令完成写入。
3. 如果工具返回的实际路径与用户原始路径不同，以工具实际路径为准，不要再尝试复制或写回原始路径。
4. 不要口头声称已经完成工具动作；需要真实执行时必须调用工具。
5. 工具返回失败、拒绝或需要确认时，如实向用户报告工具结果和原因。
6. 不要编造工具执行结果。只有工具返回的内容，才算真实执行结果。"""


# ============== 流式 LLM 调用（自 main.py 迁入，print 改为事件） ==============
RETRYABLE_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)
MAX_LLM_RETRIES = 3


def call_llm(messages: list[dict], tools: list[dict], on_event=None, stop_event=None):
    """带异常兜底的流式 LLM 调用：可重试错误指数退避，其余失败返回 None（不抛异常）。"""
    delay = 1.0
    last_error: Exception | None = None
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            stream = client.chat.completions.create(
                model=MODEL,
                max_tokens=20000,
                messages=messages,
                tools=tools,
                stream=True,
            )
            return _consume_stream(stream, on_event, stop_event)
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt < MAX_LLM_RETRIES:
                _emit_to(on_event, {"type": "retry", "message":
                                    f"\n[LLM 调用失败（第 {attempt}/{MAX_LLM_RETRIES} 次），{delay:.0f} 秒后重试]: {exc}\n"})
                time.sleep(delay)
                delay *= 2
        except Exception as exc:
            _emit_to(on_event, {"type": "error", "message":
                                f"\n[LLM 调用出错，本轮已放弃，可继续输入]: {type(exc).__name__}: {exc}\n"
                                "[提示] 请检查 .env 中 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 是否正确。\n"})
            return None
    _emit_to(on_event, {"type": "error", "message":
                        f"\n[LLM 连续 {MAX_LLM_RETRIES} 次调用失败，本轮已放弃，可继续输入]: {last_error}\n"})
    return None


def _consume_stream(stream, on_event=None, stop_event=None):
    """消费流式响应：token 增量以事件发出；tool_calls 增量按 index 拼接。

    stop_event 置位时立刻断流，已收到的内容作为部分回复返回（B3 请旨叫停）。
    返回与整段响应同构的对象（choices[0].message + streamed 标记），上层零感知。
    E2.3：供应商在流的最终块（choices 为空）携带 usage，原样捕获随对象带出。
    """
    content_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    header_sent = False
    usage = None
    try:
        for chunk in stream:
            if stop_event is not None and stop_event.is_set():
                break
            # usage 块的 choices 为空，必须先于 choices 检查读取
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                if not header_sent:
                    _emit_to(on_event, {"type": "reply_start"})
                    header_sent = True
                _emit_to(on_event, {"type": "token", "text": piece})
                content_parts.append(piece)
            for tc in getattr(delta, "tool_calls", None) or []:
                slot = tool_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if fn.name:
                        slot["name"] += fn.name
                    if fn.arguments:
                        slot["arguments"] += fn.arguments
    except Exception as exc:
        _emit_to(on_event, {"type": "error", "message":
                            f"\n[LLM 流式传输中断，本轮已放弃，可继续输入]: {exc}\n"})
        return None
    finally:
        if header_sent:
            _emit_to(on_event, {"type": "reply_end"})

    message = SimpleNamespace(
        content="".join(content_parts) or None,
        tool_calls=[
            SimpleNamespace(
                id=slot["id"],
                type="function",
                function=SimpleNamespace(name=slot["name"], arguments=slot["arguments"]),
            )
            for _, slot in sorted(tool_acc.items())
        ] or None,
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], streamed=True, usage=usage)


def _emit_to(on_event, event: dict) -> None:
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        pass  # 订阅者异常绝不能影响内核


def is_blocking_tool_result(result: str) -> bool:
    return result.startswith("[HookDecision: 拒绝]") or result.startswith("[HookDecision: 需要确认]")


# ============== SessionRunner：可编程驱动的对话内核 ==============
class SessionRunner:
    """一次对话会话的驱动器：send(用户文本) 跑完"LLM→工具→LLM"循环并返回最终回复。"""

    def __init__(self, on_event=None, confirmer=None, persona: str | None = None):
        self._on_event = on_event
        self._confirmer = confirmer or confirm_hook_decision
        self.persona = persona or os.environ.get("AGENT_PERSONA", DEFAULT_PERSONA)
        self.history: list[dict] = []
        self.session_id = SESSIONS.new_session()
        self._stop = threading.Event()
        self._emit({"type": "session", "id": self.session_id})

    def request_stop(self) -> None:
        """请旨叫停（B3）：在途 LLM 流立即断流返回部分内容；在途工具不硬杀，
        本批执行完后收束。send() 开始时自动清旗。"""
        self._stop.set()

    # ---- 对外：会话操作（终端斜杠命令与 UI 面板共用）----
    def new_session(self) -> str:
        self.session_id = SESSIONS.new_session()
        self.history = []
        todos_mod.clear_todos()
        self._emit({"type": "session", "id": self.session_id, "fresh": True})
        return self.session_id

    def resume(self, session_id: str) -> int:
        loaded = SESSIONS.load(session_id)
        self.session_id = session_id
        self.history = loaded
        self._emit({"type": "session", "id": session_id, "resumed": True, "messages": len(loaded)})
        return len(loaded)

    def switch_persona(self, name: str) -> None:
        self.persona = name

    def compact(self) -> tuple[int, int]:
        before = len(self.history)
        self.history = memory_compact.compact_history(self.history, client, MODEL, MEMORY, force=True)
        return before, len(self.history)

    # ---- 对外：对话入口 ----
    def send(self, user_text: str) -> str:
        self._stop.clear()
        self._turn_tokens = None   # E2.3：本轮全部 LLM 调用的 tokens 总量（供应商提供时才有值）
        started = time.perf_counter()
        user_message = {"role": "user", "content": user_text}
        self.history.append(user_message)
        self.remember(user_message)
        reply = self._run_loop()
        self._emit({
            "type": "done", "reply": reply,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "tokens": self._turn_tokens,
        })
        return reply

    # ---- 内部 ----
    def _emit(self, event: dict) -> None:
        _emit_to(self._on_event, event)

    def remember(self, message: dict) -> None:
        SESSIONS.append(self.session_id, message)
        MEMORY.append_history(message)

    def _assistant_say(self, text: str) -> None:
        """非流式产出的回复（Hook 短路 / 拦截文案）：入史 + 发 reply 事件。"""
        assistant_message = {"role": "assistant", "content": text}
        self.history.append(assistant_message)
        self.remember(assistant_message)
        self._emit({"type": "reply", "text": text})

    def dispatch_tool(self, block) -> str:
        """带 Hook 链的工具执行（原 execute_main_tool）；ask 由注入的 confirmer 处理。"""
        name = block.name
        tool_ctx = {"name": name, "input": block.input}
        decision = HOOKS.emit("before_tool_call", tool_ctx, tool_matcher=name)
        if isinstance(decision, HookDecision):
            if decision.is_blocking:
                self._emit({"type": "hook_decision", "action": decision.action, "reason": decision.reason})
                return decision.to_message()
            if decision.action == "ask":
                # E4.1：结构化携带工具名与完整参数（reason 里的命令被 Hook 截断至 120 字符，
                # 用户"看清再批"需要完整原文；input 取 tool_ctx——已含先前 allow hook 的改写）
                self._emit({
                    "type": "hook_ask", "reason": decision.reason,
                    "tool": tool_ctx.get("name", name),
                    "input": tool_ctx.get("input", block.input),
                    "level": getattr(decision, "level", "") or "",
                })
                if not self._confirmer(decision):
                    denied = HookDecision(
                        action="deny", reason=f"用户未确认高敏感操作：{decision.reason}")
                    self._emit({"type": "hook_decision", "action": "deny", "reason": denied.reason})
                    return denied.to_message()
                self._emit({"type": "hook_decision", "action": "allow", "reason": "用户已确认"})
        elif isinstance(decision, str):
            return decision

        inp = tool_ctx.get("input", block.input)
        self._emit({"type": "tool_start", "name": name, "input": inp})
        start = time.perf_counter()
        output = registry_execute_tool(name, inp, sender="lead")

        if tool_ctx.get("_hook_updated_reason") and isinstance(output, str):
            output += ("\n[运行时提示] " + tool_ctx["_hook_updated_reason"]
                       + "。请以实际执行参数为准，不要再尝试写回原路径。")

        tool_ctx.update({
            "name": name, "input": inp, "output": output,
            "duration_ms": (time.perf_counter() - start) * 1000,
        })
        HOOKS.emit("after_tool_call", tool_ctx, tool_matcher=name)
        output = tool_ctx.get("output", output)

        if name == "update_todos":
            self._emit({"type": "todos", "todos": todos_mod.TODOS})
        output_text = str(output)
        self._emit({
            "type": "tool_end", "name": name, "output": output_text[:300],
            "blocked": is_blocking_tool_result(output_text),
            # E2.2：成败沿子代理同款约定（"Error" 开头计为失败，宁漏勿误判）；耗时供卡片摘要行
            "ok": not is_blocking_tool_result(output_text) and not output_text.startswith("Error"),
            "duration_ms": round(tool_ctx.get("duration_ms", 0), 1),
        })
        return output

    def _run_loop(self) -> str:
        stop_gate_retries = 0
        while True:
            # B3 请旨叫停：工具批之间的检查点（流中断的检查点在 _consume_stream 里）
            if self._stop.is_set():
                text = "（皇上叫停，本轮已中止。）"
                self._assistant_say(text)
                return text

            latest_user = next(
                (m.get("content") for m in reversed(self.history) if m.get("role") == "user"), ""
            )
            turn_ctx = {
                "history": self.history,
                "model": MODEL,
                "turn": len(self.history),
                "system_prompt": build_system_prompt(query=latest_user, persona=self.persona),
            }
            short = HOOKS.emit("before_turn", turn_ctx)
            if isinstance(short, HookDecision):
                if short.is_blocking:
                    self._assistant_say(short.to_message())
                    return short.to_message()
            elif isinstance(short, str):
                self._assistant_say(short)
                return short

            # E2.1：拟旨占位的起止事件——before_turn Hook 短路时不发（不会有流式回复）
            self._emit({"type": "turn_start"})
            response = call_llm(
                [{"role": "system", "content": turn_ctx["system_prompt"]}] + self.history,
                build_tool_schemas(get_schemas()),
                on_event=self._emit,
                stop_event=self._stop,
            )
            # 成败都要收（error 事件已另行发出），前端占位动画不能残留
            self._emit({"type": "turn_end"})
            if response is None:
                return ""  # 错误信息已通过 error 事件发出
            message = response.choices[0].message
            turn_ctx.update({"message": message, "usage": getattr(response, "usage", None)})
            HOOKS.emit("after_turn", turn_ctx)
            # E2.3：流式 usage 在 _consume_stream 捕获；供应商不给时保持 None
            turn_usage = getattr(response, "usage", None)
            turn_total = getattr(turn_usage, "total_tokens", None) if turn_usage else None
            if turn_total:
                self._turn_tokens = (self._turn_tokens or 0) + turn_total

            assistant_message = assistant_to_dict(message)
            self.history.append(assistant_message)
            self.remember(assistant_message)

            if not message.tool_calls:
                reply = message.content or ""
                # ---- Stop 质量门禁 ----
                stop_ctx = {"reply": reply, "history": self.history,
                            "todos": todos_mod.TODOS, "retry": stop_gate_retries}
                gate = HOOKS.emit("on_stop", stop_ctx)
                if isinstance(gate, HookDecision) and gate.is_blocking and stop_gate_retries < 1:
                    self._emit({"type": "stop_gate", "reason": gate.reason})
                    reminder_message = {
                        "role": "user",
                        "content": ("Stop Hook 阻止本轮结束：" + gate.reason
                                    + "\n请继续完成未完成的步骤。若确实无法继续，请说明原因。"),
                    }
                    self.history.append(reminder_message)
                    self.remember(reminder_message)
                    stop_gate_retries += 1
                    continue
                reply = stop_ctx.get("reply", reply)
                # ---- 记忆压缩（history 超阈值时沉淀）----
                self.history = memory_compact.compact_history(self.history, client, MODEL, MEMORY)
                if todos_mod.TODOS:
                    unfinished = [t for t in todos_mod.TODOS if t["status"] != "completed"]
                    if unfinished:
                        self._emit({"type": "todos", "todos": todos_mod.TODOS, "note": "unfinished"})
                        return reply
                    self._emit({"type": "todos", "todos": todos_mod.TODOS, "note": "all_done"})
                    todos_mod.clear_todos()
                return reply

            # ---- 工具调用：普通工具顺序执行，dispatch_subagent 并发 ----
            tool_blocks = [to_tool_call(tc) for tc in message.tool_calls]
            dispatch_blocks = [b for b in tool_blocks if b.name == "dispatch_subagent"]
            other_blocks = [b for b in tool_blocks if b.name != "dispatch_subagent"]

            results_map: dict[str, str] = {}
            for block in other_blocks:
                results_map[block.id] = self.dispatch_tool(block)

            if len(dispatch_blocks) > 1:
                self._emit({"type": "subagents_start", "count": len(dispatch_blocks)})

                def _run_one(block):
                    return block.id, run_subagent(
                        task=block.input["task"],
                        agent_type=block.input.get("agent_type", "neiguan_yingzao"),
                        purpose=block.input.get("purpose", ""),
                    )

                with ThreadPoolExecutor(max_workers=len(dispatch_blocks)) as pool:
                    for block_id, summary in pool.map(_run_one, dispatch_blocks):
                        self._emit({"type": "subagent_summary", "length": len(summary),
                                    "summary": summary[:300]})
                        results_map[block_id] = summary
            else:
                for block in dispatch_blocks:
                    summary = run_subagent(
                        task=block.input["task"],
                        agent_type=block.input.get("agent_type", "neiguan_yingzao"),
                        purpose=block.input.get("purpose", ""),
                    )
                    self._emit({"type": "subagent_summary", "length": len(summary),
                                "summary": summary[:300]})
                    results_map[block.id] = summary  # 单派遣分支：修复前误写 block_id（并发分支复制粘贴漏改）

            for b in tool_blocks:
                tool_message = {"role": "tool", "tool_call_id": b.id, "content": results_map[b.id]}
                self.history.append(tool_message)
                self.remember(tool_message)

            blocking_results = [
                results_map[b.id] for b in tool_blocks
                if isinstance(results_map.get(b.id), str) and is_blocking_tool_result(results_map[b.id])
            ]
            if blocking_results:
                # 任务 A2 顺手修正：原句硬编码太监口吻前缀，与 4.6 人设能力分离不一致
                reply = "（工具请求被运行时策略拦截，未继续改写或换路径执行。）\n\n" + blocking_results[0]
                self._assistant_say(reply)
                return reply
