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
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from openai import APIConnectionError, InternalServerError, RateLimitError  # noqa: F401  兼容旧引用

from . import llm, memory_compact, todos as todos_mod
from . import app_settings
from .config import PERSONA_DIR
from .hooks import HOOKS, HookDecision, confirm_hook_decision, is_blocking_message
from .llm import assistant_to_dict, to_tool_call   # F2：client/MODEL 一律走 llm. 属性引用（可热重建）
from .llm import RETRYABLE_ERRORS, MAX_LLM_RETRIES   # 阶段十四：口径迁 llm.py，与子代理共用
from .mcp_client import build_tool_schemas
from .memory import MEMORY
from .memory_rag import MEMORY_RAG
from .registry import execute_guarded   # 阶段十：Hook 链下沉至统一守卫入口，三执行体共用
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
10. 用户交代"记住…"或对话中出现值得长期保留的稳定事实（偏好、背景、项目约定）时，
   调用 save_memory 工具记入长期记忆；寒暄与一次性细节不要记，也不要口头声称记住了。

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
# RETRYABLE_ERRORS / MAX_LLM_RETRIES 已迁 llm.py（阶段十四：与子代理重试壳共用一口径）


def call_llm(messages: list[dict], tools: list[dict], on_event=None, stop_event=None):
    """带异常兜底的流式 LLM 调用：可重试错误指数退避，其余失败返回 None（不抛异常）。"""
    delay = 1.0
    last_error: Exception | None = None
    if llm.client is None:
        _emit_to(on_event, {"type": "error", "message":
                            "\n[未配置模型] 请在界面「模型阁」添加模型配置（接口地址 / API Key / 模型名），"
                            "或在 .env 配置 LLM_* 后重启。\n"})
        return None
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            stream = llm.client.chat.completions.create(
                model=llm.MODEL,
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
    reasoning_sent = False   # G4：思维链只发一次 start
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
            # G4：思维链（DeepSeek 系 delta.reasoning_content）流式转发，不写入 history
            piece_r = getattr(delta, "reasoning_content", None)
            if piece_r:
                if not reasoning_sent:
                    _emit_to(on_event, {"type": "reasoning_start"})
                    reasoning_sent = True
                _emit_to(on_event, {"type": "reasoning", "text": piece_r})
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


# ============== SessionRunner：可编程驱动的对话内核 ==============
class SessionRunner:
    """一次对话会话的驱动器：send(用户文本) 跑完"LLM→工具→LLM"循环并返回最终回复。"""

    def __init__(self, on_event=None, confirmer=None, persona: str | None = None,
                 ephemeral: bool = False):
        self._on_event = on_event
        self._confirmer = confirmer or confirm_hook_decision
        # 阶段九：默认人格走内务府设置（settings.json 覆盖 .env 种子），每次建连接现读
        self.persona = persona or app_settings.load().get("default_persona") or DEFAULT_PERSONA
        self.history: list[dict] = []
        # 阶段十三：密折——不入名册、不留记忆、关窗即焚。id 用 mi- 前缀且不走 SESSIONS
        # 登记（文件懒创建，remember 短路后自然无文件）；写入口子见 remember/压缩/题名。
        self.ephemeral = ephemeral
        self.session_id = (f"mi-{datetime.now():%Y%m%d-%H%M%S}" if ephemeral
                           else SESSIONS.new_session())
        self._stop = threading.Event()
        self._usage = self._fresh_usage()   # E5 内库账房：本次连接的用度账本
        self._titled = False                # G2：本会话是否已命名
        self._emit({"type": "session", "id": self.session_id, "ephemeral": ephemeral})

    @staticmethod
    def _fresh_usage() -> dict:
        return {"turns": 0, "prompt": 0, "completion": 0, "cache_hit": 0,
                "last_prompt": None, "last_total": None}

    def _usage_acc(self, usage) -> None:
        """累加一次 LLM 调用的 usage（E5）。字段缺失（非 DeepSeek 供应商）按 0 计，
        前端对 0/None 显示"—"，不报错。"""
        u = self._usage
        u["turns"] += 1
        u["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
        u["completion"] += getattr(usage, "completion_tokens", 0) or 0
        u["cache_hit"] += getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        u["last_prompt"] = getattr(usage, "prompt_tokens", None)
        u["last_total"] = getattr(usage, "total_tokens", None)

    def request_stop(self) -> None:
        """请旨叫停（B3）：在途 LLM 流立即断流返回部分内容；在途工具不硬杀，
        本批执行完后收束。send() 开始时自动清旗。"""
        self._stop.set()

    # ---- 对外：会话操作（终端斜杠命令与 UI 面板共用）----
    def new_session(self) -> str:
        self.ephemeral = False   # 密折开新殿即转正
        self.session_id = SESSIONS.new_session()
        self.history = []
        self._usage = self._fresh_usage()   # E5：开新殿账本归零
        self._titled = False
        todos_mod.clear_todos()
        self._emit({"type": "session", "id": self.session_id, "fresh": True, "ephemeral": False})
        return self.session_id

    def resume(self, session_id: str) -> int:
        loaded = SESSIONS.load(session_id)
        self.ephemeral = False   # 密折里 /resume 旧殿即转正
        self.session_id = session_id
        self.history = loaded
        self._usage = self._fresh_usage()   # E5：resume 归零重计（旧轮次成本未重放，诚实口径）
        self._titled = bool(SESSIONS.get_title(session_id))   # 旧殿已有题名则不再起
        self._emit({"type": "session", "id": session_id, "resumed": True,
                    "messages": len(loaded), "ephemeral": False})
        return len(loaded)

    def switch_persona(self, name: str) -> None:
        self.persona = name

    def compact(self) -> tuple[int, int]:
        before = len(self.history)
        if self.ephemeral:   # 密折不沉淀：压缩会写 MEMORY.md，违背"不留记忆"
            return before, before
        self.history = memory_compact.compact_history(self.history, llm.client, llm.MODEL, MEMORY, force=True)
        return before, len(self.history)

    # ---- 对外：对话入口 ----
    def send(self, user_text: str) -> str:
        self._stop.clear()
        user_message = {"role": "user", "content": user_text}
        self.history.append(user_message)
        try:
            self.remember(user_message)
            return self._finish_round()
        except Exception as exc:
            # 阶段十一（入口级网）：炸在序备段（remember，如 4.5 的递归事故位置）也能收束
            return self._crash_landing(exc)

    # ---- G3：另拟 / 改旨 ----
    # ---- G3：另拟 / 改旨 ----
    SYNTHETIC_USER_PREFIXES = (
        "Stop Hook 阻止本轮结束",          # Stop 门禁自动注入的提醒
        "部分工具被运行时策略拦截",        # 阶段十四：批量拦截后的防重试提醒
    )

    def _last_real_user_index(self) -> int | None:
        """最后一条真实用户消息的下标（跳过内核自动注入的合成提醒，另拟/改旨不把它当圣谕）。"""
        for i in range(len(self.history) - 1, -1, -1):
            m = self.history[i]
            if m.get("role") == "user" and not str(m.get("content", "")).startswith(
                    self.SYNTHETIC_USER_PREFIXES):
                return i
        return None

    def regenerate(self) -> str:
        """另拟：丢弃最后一条用户消息之后的全部内容（保留该消息），重跑本轮。"""
        self._stop.clear()
        idx = self._last_real_user_index()
        if idx is None:
            return ""
        self.history = self.history[:idx + 1]
        try:
            if not self.ephemeral:   # 密折无会话文件，truncate 跳过
                SESSIONS.truncate(self.session_id, len(self.history))
            return self._finish_round()
        except Exception as exc:
            return self._crash_landing(exc)

    def edit_last(self, new_text: str) -> str:
        """改旨：撤回最后一条用户消息（连同其回复），换成新文本重跑。"""
        self._stop.clear()
        idx = self._last_real_user_index()
        if idx is None:
            return self.send(new_text)
        self.history = self.history[:idx]
        try:
            if not self.ephemeral:   # 密折无会话文件，truncate 跳过
                SESSIONS.truncate(self.session_id, len(self.history))
            user_message = {"role": "user", "content": new_text}
            self.history.append(user_message)
            self.remember(user_message)
            return self._finish_round()
        except Exception as exc:
            return self._crash_landing(exc)

    def _finish_round(self) -> str:
        """send/regenerate/edit_last 共用的收束：计时跑主循环、发 done、起标题。"""
        self._turn_tokens = None   # E2.3：本轮全部 LLM 调用的 tokens 总量（供应商提供时才有值）
        started = time.perf_counter()
        try:
            reply = self._run_loop()
        except Exception as exc:
            # 阶段十一（轮级兜底）：单轮崩溃降级为"报错后继续会话"——进程不死、会话不废
            reply = self._crash_landing(exc)
        self._emit({
            "type": "done", "reply": reply,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "tokens": self._turn_tokens,
            # E5 内库账房：本次连接的累计用度 + 模型窗口（前端算占用率）
            "usage": dict(self._usage),
            "context_window": llm.CONTEXT_WINDOW,
        })
        self._maybe_title(reply)
        return reply

    # ---- 阶段十一：轮级异常兜底 ----
    def _crash_landing(self, exc: Exception) -> str:
        """轮级兜底落点：发 error 事件 → 补历史悬空 → 拼说明入史，返回收束文案。

        网自身全程防御：兜底路径再炸（如 4.5 那种 remember 递归）也不能击穿——
        error 事件先发，落盘类动作各自包 try，最坏情况只是会话文件来不及修正。
        """
        self._emit({"type": "error", "message":
                    f"\n[内核轮级异常，本轮已安全收束，会话可继续]: {type(exc).__name__}: {exc}\n"})
        try:
            self._patch_dangling_tool_calls(f"（内部异常：{type(exc).__name__}: {exc}）")
        except Exception:
            pass
        text = f"（本轮内部出错已收束：{type(exc).__name__}: {exc}。会话可继续，请重新传旨或另拟。）"
        try:
            self._assistant_say(text)
        except Exception:
            pass
        return text

    def _patch_dangling_tool_calls(self, note: str) -> int:
        """给 history 尾部悬空的 tool_calls 补配对 tool 消息（含会话文件），返回补了几条。

        悬空只可能出现在尾部：工具消息在批后立即写入，崩溃中断的正是"没写完的批"。
        漏配对会让下一轮请求被 API 400 打回（协议不变量：role=tool 必须紧跟
        带 tool_calls 的 assistant），所以收束前必须补齐。
        """
        idx = len(self.history) - 1
        while idx >= 0 and self.history[idx].get("role") == "tool":
            idx -= 1
        if idx < 0:
            return 0
        tail = self.history[idx]
        tool_calls = tail.get("tool_calls") or []
        if tail.get("role") != "assistant" or not tool_calls:
            return 0
        answered = {m.get("tool_call_id") for m in self.history[idx + 1:]
                    if m.get("role") == "tool"}
        patched = 0
        for tc in tool_calls:
            tc_id = tc.get("id")
            if tc_id and tc_id not in answered:
                msg = {"role": "tool", "tool_call_id": tc_id,
                       "content": f"Error: 工具批执行中断，未获得结果。{note[:200]}"}
                self.history.append(msg)
                self.remember(msg)
                patched += 1
        return patched

    # ---- G2：会话自动命名 ----
    def _maybe_title(self, reply: str) -> None:
        """新会话第一轮结束后用一次微型 LLM 调用起 ≤10 字标题；失败静默（标题缺失不影响对话）。

        H1：用户手动改过名的会话（custom_titles）不参与自动题名——皇上的朱笔大过老奴的题名。
        """
        if self._titled or not reply.strip() or llm.client is None or self.ephemeral:
            return   # 密折不题名：titles.json 也是记录（阶段十三）
        if SESSIONS.is_custom(self.session_id):
            self._titled = True   # 本连接内不再重试
            return
        user_text = next((m.get("content") for m in reversed(self.history)
                          if m.get("role") == "user"), "")
        try:
            resp = llm.client.chat.completions.create(
                # 推理模型会把 token 先花在思维链上，上限太小会导致正文为空
                model=llm.MODEL, max_tokens=1024, temperature=0,
                messages=[
                    {"role": "system",
                     "content": "给这段对话起一个不超过10字的中文标题。只输出标题本身，不要引号、句号或任何解释。"},
                    {"role": "user", "content": f"{user_text}\n\n（助手回复开头：{reply[:80]}）"},
                ],
            )
            title = (resp.choices[0].message.content or "").strip().splitlines()[0].strip()
            title = title.strip('"「」『』。，,')[:16]
        except Exception:
            return
        if title:
            self._titled = True
            SESSIONS.set_title(self.session_id, title)
            self._emit({"type": "session_title", "id": self.session_id, "title": title})

    # ---- 内部 ----
    def _emit(self, event: dict) -> None:
        _emit_to(self._on_event, event)

    def remember(self, message: dict) -> None:
        if self.ephemeral:
            return   # 密折：会话文件与 history.jsonl 双不写（阶段十三）
        SESSIONS.append(self.session_id, message)
        MEMORY.append_history(message)

    def _assistant_say(self, text: str) -> None:
        """非流式产出的回复（Hook 短路 / 拦截文案 / 兜底说明）：入史 + 发 reply 事件。

        先落盘再改内存史：remember 失败时 history 尾部不残留未持久化的半截状态。
        """
        assistant_message = {"role": "assistant", "content": text}
        self.remember(assistant_message)
        self.history.append(assistant_message)
        self._emit({"type": "reply", "text": text})

    @staticmethod
    def _parse_tool_blocks(raw_tool_calls, results_map: dict) -> list:
        """逐个解析 tool_calls 为执行块；解析失败的就地写一条 Error tool 消息并跳过。

        阶段十一（协议保对）：arguments 是流式按 index 拼回的字符串，max_tokens 截断
        或模型抽风都会产出残缺 JSON——若在这里崩掉，已入史的 assistant 消息就成了
        悬空调用，下一轮请求会被 API 400 打回。坏参数以 Error tool 消息回给模型，
        让它修正后重试，同批其余调用不受牵连。
        """
        blocks = []
        for tc in raw_tool_calls:
            try:
                block = to_tool_call(tc)
                if not isinstance(block.input, dict):
                    raise ValueError(f"工具参数应为 JSON 对象，实为 {type(block.input).__name__}")
            except Exception as exc:
                results_map[tc.id] = (f"Error: 工具参数解析失败，本次调用未执行"
                                      f"（{type(exc).__name__}: {exc}）。请修正参数后重试。")
                continue
            blocks.append(block)
        return blocks

    def dispatch_tool(self, block) -> str:
        """带 Hook 链的工具执行。

        链本体（before 决策 / ask 确认 / 执行 / after 截断 / tool_start、tool_end 事件）
        在 registry.execute_guarded（阶段十三端收编）；这里只补主循环会话层的
        todos 联动事件，并注入 UI 的确认回调（圣旨弹窗 / 终端 input）。
        """
        if self.ephemeral and block.name in ("save_memory", "spawn_teammate"):
            # 阶段十三：密折不立言、不设班底——两个"写盘留痕"的工具直接拒
            return ("Error: 密折模式下不可使用该工具（临时交谈不入名册、不留记忆、不召固定队友）。"
                    "请如实向皇上说明，或请皇上开正式偏殿后再办。")
        output = execute_guarded(
            block.name, block.input, sender="lead",
            on_event=self._emit, confirmer=self._confirmer,
        )
        if block.name == "update_todos":
            self._emit({"type": "todos", "todos": todos_mod.TODOS})
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
                "model": llm.MODEL,
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
            if turn_usage is not None:
                self._usage_acc(turn_usage)   # E5：入账本

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
                if not self.ephemeral:   # 密折不沉淀：压缩会把旧对话写进 MEMORY.md（阶段十三）
                    _before = len(self.history)
                    self.history = memory_compact.compact_history(self.history, llm.client, llm.MODEL, MEMORY)
                    if len(self.history) < _before:   # G1：压缩对用户可见
                        self._emit({"type": "memory_compacted", "removed": _before - len(self.history)})
                if todos_mod.TODOS:
                    unfinished = [t for t in todos_mod.TODOS if t["status"] != "completed"]
                    if unfinished:
                        self._emit({"type": "todos", "todos": todos_mod.TODOS, "note": "unfinished"})
                        return reply
                    self._emit({"type": "todos", "todos": todos_mod.TODOS, "note": "all_done"})
                    todos_mod.clear_todos()
                return reply

            # ---- 工具调用：普通工具顺序执行，dispatch_subagent 并发 ----
            # 阶段十一（协议保对）：坏参数就地回 Error tool 消息，同批其余照常执行
            results_map: dict[str, str] = {}
            tool_blocks = self._parse_tool_blocks(message.tool_calls, results_map)
            dispatch_blocks = [b for b in tool_blocks if b.name == "dispatch_subagent"]
            other_blocks = [b for b in tool_blocks if b.name != "dispatch_subagent"]
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

            # 按 model 给出的顺序回填全部 tool 结果——含解析失败的坏 id（协议保对：
            # results_map 里此刻覆盖了每一个 tool_call_id，缺一条都是悬空）
            for tc in message.tool_calls:
                tool_message = {"role": "tool", "tool_call_id": tc.id, "content": results_map[tc.id]}
                self.history.append(tool_message)
                self.remember(tool_message)

            blocking_results = [
                results_map[b.id] for b in tool_blocks
                if isinstance(results_map.get(b.id), str) and is_blocking_message(results_map[b.id])
            ]
            if blocking_results:
                # 阶段十四（债③）：不再整轮终止——工具消息已全部入史（含拒绝原因与同批成功
                # 结果），注入防重试提醒后继续循环，让模型如实汇报未受阻的部分。
                # 固定文案替模型说话会陪葬成功结果，违背行事规矩第 5 条（4.1 实测留痕）。
                reminder = {
                    "role": "user",
                    "content": ("部分工具被运行时策略拦截（原因见对应工具回执）。"
                                "请如实向皇上汇报本批其余工具的执行结果；"
                                "不要改写参数、不要换路径、不要重试被拦的操作。"),
                }
                self.history.append(reminder)
                self.remember(reminder)
