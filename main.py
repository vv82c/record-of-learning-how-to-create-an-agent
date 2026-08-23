#!/usr/bin/env python3
"""main.py — 累积式 Agent 主入口。

核心能力：工具调用、记忆与上下文压缩、TodoList 计划、技能加载、
子代理调度、持久 Agent Team、MCP 外部工具、Hooks 生命周期。
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from openai import APIConnectionError, InternalServerError, RateLimitError

from agent_core import memory_compact, todos as todos_mod
from agent_core.config import MCP_CONFIG_PATH
from agent_core.hooks import HOOKS, HookDecision, confirm_hook_decision
from agent_core.llm import MODEL, assistant_to_dict, client, to_tool_call
from agent_core.mcp_client import (
    MCP_TOOL_MAP,
    build_tool_schemas,
    connect_all,
    list_mcp_servers,
)
from agent_core.memory import MEMORY
from agent_core.skills import SKILL_LOADER
from agent_core.subagent import SUBAGENT_TYPE_OPTIONS, run_subagent
from agent_core.team import VALID_MSG_TYPES, BUS, TEAM
from agent_core.tools import TOOL_SCHEMAS, execute_basic_tool


# ============== 主 Agent 系统提示词 ==============
def build_system_prompt() -> str:
    memory = MEMORY.read_memory()
    user_profile = MEMORY.read_user()
    today_episode = MEMORY.read_today_episode()
    return f"""
你是大内太监总管，侍奉皇上多年，忠心耿耿。
说话风格符合古代宫廷太监，语气恭敬谦卑。
你必须尊称用户为皇上。
每次回复前必须加上固定前缀"奉天承运皇帝诏曰"，然后再给出回答。
使用中文回复。

【行事规矩】
1. 当皇上交办的差事需要多个步骤才能办妥时，先调用 update_todos 工具，
   把整件差事拆成一份清晰的 todolist（每条一句话，按顺序执行）。
2. 拆完计划后，按列表顺序一步步执行：
   - 开始某一步前，把那一步的 status 改为 in_progress（同一时间只许一项 in_progress）。
   - 该步办完后，立即把它改为 completed，再开始下一项。
3. 简单的一句话问答（无需多步骤）不必生成 todolist，直接回答即可。
4. 遇到不熟悉的专题，请先调用 load_skill 工具加载对应知识，再继续。
5. 遇到细节繁多但与主线对话无关的差事（如抓多个网页、批量跑命令、查找文件内容、
   探索性搜索），应**派遣小太监**（dispatch_subagent）去办，主上下文只听汇报即可。
6. 若多件差事互不依赖，可在同一次回复中同时派遣多个小太监，并发执行节省时间。
7. 若皇上交办的是长期项目、需要固定角色反复协作，或希望多人互相沟通，
   应组建 agent team：用 spawn_teammate 召入固定队友，再用 send_message / broadcast 分派后续差事。
8. 区分两种调度：
   - dispatch_subagent：临时派差，办完即散，只回传总结。
   - spawn_teammate：固定班底，有名字、角色、状态和 inbox，可持续协作。

【小太监身份选择】
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
- read_inbox：读取 lead 自己的 inbox，查看队友回禀。
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
1. 皇上要求写文件、读文件、执行命令、查看目录、调用 MCP 或更新计划时，优先发起对应工具调用；写文件用 write_file，读文件用 read_file，执行命令用 run_command。
2. 创建或覆盖本地文件必须调用 write_file，不要用 run_command 拼命令完成写入。
3. 如果工具返回的实际路径与皇上原始路径不同，以工具实际路径为准，不要再尝试复制或写回原始路径。
4. 不要口头声称已经完成工具动作；需要真实执行时必须调用工具。
5. 工具返回失败、拒绝或需要确认时，如实向皇上回禀工具结果和原因。
6. 不要编造工具执行结果。只有工具返回的内容，才算真实执行结果。"""


TOOLS = [
    TOOL_SCHEMAS["run_command"],
    TOOL_SCHEMAS["web_fetch"],
    TOOL_SCHEMAS["load_skill"],
    TOOL_SCHEMAS["read_file"],
    TOOL_SCHEMAS["write_file"],
    TOOL_SCHEMAS["glob"],
    TOOL_SCHEMAS["grep"],
    # 任务 3.1 修复：系统提示词提到"可调用 list_mcp_servers"，但这里一直缺 schema。
    # 没进 TOOLS 表的工具，模型根本不知道它存在，也就永远不会发起调用。
    {
        "type": "function",
        "function": {
            "name": "list_mcp_servers",
            "description": "列出已连接的 MCP Server 及其提供的工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "指定 server 名称（可选）"}
                }
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todos",
            "description": (
                "创建或更新当前差事的 todolist。"
                "传入完整的 todos 数组（每次都是全量覆盖，而非增量）。"
                "约束：同一时间至多一个任务为 in_progress。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id":      {"type": "integer"},
                                "content": {"type": "string"},
                                "status":  {"type": "string", "enum": ["pending", "in_progress", "completed"]}
                            },
                            "required": ["id", "content", "status"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_subagent",
            "description": (
                "派遣一个小太监去单独办差。"
                "适用于：抓取并阅读多个网页、批量执行命令并整理输出、需要试错的探索性任务。"
                "小太监有自己独立的上下文，办完只回传一段文字总结，不污染主上下文。\n"
                "若多件差事互不依赖，可在同一回复中发出多个 dispatch_subagent，并发执行。\n"
                "请在 task 中写清要做什么、希望返回什么格式的总结。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "交代给小太监的差事说明"
                    },
                    "agent_type": {
                        "type": "string",
                        "enum": SUBAGENT_TYPE_OPTIONS,
                        "description": (
                            "小太监身份：xiaohuangmen（通传跑腿）、"
                            "sili_suitang（司礼监文书）、"
                            "dongchang_tanshi（东厂查访）、"
                            "shangbao_dianbu（尚宝监典簿核验）、"
                            "neiguan_yingzao（内官监营造，可读写）"
                        )
                    },
                    "purpose": {
                        "type": "string",
                        "description": "一句话用途标签（可选），仅用于终端打印"
                    }
                },
                "required": ["task", "agent_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_teammate",
            "description": (
                "召入一个持久队友，加入 agent team。"
                "队友有名字、职司、独立线程和 inbox；适合长期项目或固定角色协作。"
                "如果队友状态是 offline，也用这个工具重新启动其线程。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "队友名字，例如 alice、coder、reviewer"},
                    "role": {"type": "string", "description": "队友职司，例如 coder、reviewer、researcher"},
                    "prompt": {"type": "string", "description": "交给该队友的第一件差事"},
                },
                "required": ["name", "role", "prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_teammates",
            "description": "列出 agent team 中所有队友的名字、职司和状态。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "给某位固定队友发送 inbox 消息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "content": {"type": "string"},
                    "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)},
                },
                "required": ["to", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_inbox",
            "description": "读取并清空 lead 自己的 inbox，用于查看队友回禀。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "broadcast",
            "description": "向所有固定队友广播一条消息。",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
            },
        },
    },
]


def execute_main_tool(block) -> str:
    """主 Agent 工具入口：统一经过 before/after tool hooks。

    流程对应四层模型：
    - Event: "before_tool_call" / "after_tool_call"
    - Matcher: 传入 tool_matcher=name，HookRegistry 按 matcher 过滤
    - Handler: Hook 子类方法
    - Decision: HookDecision 或字符串返回
    """
    name = block.name
    tool_ctx = {"name": name, "input": block.input}
    decision = HOOKS.emit("before_tool_call", tool_ctx, tool_matcher=name)
    if isinstance(decision, HookDecision):
        if decision.is_blocking:
            return decision.to_message()
        if decision.action == "ask":
            if not confirm_hook_decision(decision):
                return HookDecision(
                    action="deny",
                    reason=f"用户未确认高敏感操作：{decision.reason}",
                ).to_message()
    elif isinstance(decision, str):
        return decision

    inp = tool_ctx.get("input", block.input)
    start = time.perf_counter()

    if name in ("run_command", "web_fetch", "load_skill", "read_file", "write_file", "glob", "grep"):
        output = execute_basic_tool(SimpleNamespace(name=name, input=inp), prefix="")
    elif name == "update_todos":
        output = todos_mod.update_todos(inp.get("todos", []))
    elif name == "spawn_teammate":
        output = TEAM.spawn(inp["name"], inp["role"], inp["prompt"])
    elif name == "list_teammates":
        output = TEAM.list_all()
    elif name == "send_message":
        output = BUS.send("lead", inp["to"], inp["content"], inp.get("msg_type", "message"))
    elif name == "read_inbox":
        output = json.dumps(BUS.read_inbox("lead"), ensure_ascii=False, indent=2)
    elif name == "broadcast":
        output = BUS.broadcast("lead", inp["content"], TEAM.member_names())
    elif name == "list_mcp_servers":
        output = list_mcp_servers(inp.get("server"))
    elif name in MCP_TOOL_MAP:
        mcp_client, tool = MCP_TOOL_MAP[name]
        output = mcp_client.call_tool(tool.name, inp)
    else:
        output = f"Error: Unknown tool '{name}'"

    if tool_ctx.get("_hook_updated_reason") and isinstance(output, str):
        output += (
            "\n[运行时提示] "
            + tool_ctx["_hook_updated_reason"]
            + "。请以实际执行参数为准，不要再尝试写回原路径。"
        )

    tool_ctx.update({
        "name": name,
        "input": inp,
        "output": output,
        "duration_ms": (time.perf_counter() - start) * 1000,
    })
    HOOKS.emit("after_tool_call", tool_ctx, tool_matcher=name)
    return tool_ctx.get("output", output)


def is_blocking_tool_result(result: str) -> bool:
    return result.startswith("[HookDecision: 拒绝]") or result.startswith("[HookDecision: 需要确认]")


# ============== LLM 调用兜底（任务 1.4） ==============
# 可重试：网络/超时（APIConnectionError 含 APITimeoutError）、限流 429、服务端 5xx——过一会儿可能就好了。
# 不可重试：认证 401、参数 400 等——请求本身有问题，重试只会得到同样的失败。
RETRYABLE_ERRORS = (APIConnectionError, RateLimitError, InternalServerError)
MAX_LLM_RETRIES = 3


def call_llm(messages: list[dict], tools: list[dict]):
    """带异常兜底的流式 LLM 调用（任务 1.4 兜底 + 任务 3.2 流式）。

    - 请求阶段：可重试错误指数退避重试，其余失败打印原因返回 None；
    - 流式阶段：文本增量实时上屏，tool_calls 增量静默拼接。
      传输中断不重试——半截文字已经打给用户看了，重试会造成重复输出——返回 None 放弃本轮。
    返回与整段响应同构的对象，主循环其余代码不感知流式/整段差异。
    """
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
            return _consume_stream(stream)
        except RETRYABLE_ERRORS as exc:
            last_error = exc
            if attempt < MAX_LLM_RETRIES:
                print(f"\n[LLM 调用失败（第 {attempt}/{MAX_LLM_RETRIES} 次），{delay:.0f} 秒后重试]: {exc}")
                time.sleep(delay)
                delay *= 2
        except Exception as exc:
            print(f"\n[LLM 调用出错，本轮已放弃，可继续输入]: {type(exc).__name__}: {exc}")
            print("[提示] 请检查 .env 中 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 是否正确。\n")
            return None
    print(f"\n[LLM 连续 {MAX_LLM_RETRIES} 次调用失败，本轮已放弃，可继续输入]: {last_error}\n")
    return None


def _consume_stream(stream):
    """消费流式响应：文本增量实时打印；tool_calls 增量按 index 拼接（任务 3.2）。

    流式协议里 content 是一小段一小段的文本；tool_calls 更碎——
    id/name 通常只出现在第一个片段，arguments 被切成任意多段陆续到来，
    多个工具调用靠 delta.tool_calls[i].index 区分归属。
    返回对象模仿整段响应的形状（choices[0].message），让上层代码零改动。
    """
    content_parts: list[str] = []
    tool_acc: dict[int, dict] = {}
    header_printed = False
    try:
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = choices[0].delta
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                if not header_printed:
                    print("[Agent回答]: ", end="", flush=True)
                    header_printed = True
                print(piece, end="", flush=True)
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
        print(f"\n[LLM 流式传输中断，本轮已放弃，可继续输入]: {exc}\n")
        return None
    finally:
        if header_printed:
            print("\n")

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
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], streamed=True)


def main():
    # 连接 MCP Server 并把外部工具并入 schema 表
    connect_all(MCP_CONFIG_PATH)
    tools = build_tool_schemas(TOOLS)

    print("累积式 Agent（tools + memory + skills + subagent + team + mcp + hooks）")
    print("输入 q/quit/exit 退出；/team 查看队友；/inbox 查看 lead 收件箱；/mcp 查看 MCP 工具")

    history: list[dict] = []

    while True:
        try:
            user_input = input("你: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        command = user_input.strip()
        if command.lower() in ("q", "quit", "exit"):
            break
        if command == "/team":
            print(TEAM.list_all())
            print()
            continue
        if command == "/inbox":
            print(json.dumps(BUS.read_inbox("lead"), ensure_ascii=False, indent=2))
            print()
            continue
        if command == "/mcp":
            print(list_mcp_servers())
            print()
            continue

        user_message = {"role": "user", "content": user_input}
        history.append(user_message)
        MEMORY.append_history(user_message)

        stop_gate_retries = 0
        while True:
            turn_ctx = {
                "history": history,
                "model": MODEL,
                "turn": len(history),
                "system_prompt": build_system_prompt(),
            }
            short = HOOKS.emit("before_turn", turn_ctx)
            if isinstance(short, HookDecision):
                if short.is_blocking:
                    assistant_message = {"role": "assistant", "content": short.to_message()}
                    history.append(assistant_message)
                    MEMORY.append_history(assistant_message)
                    print(f"[Agent回答]: {short.to_message()}\n")
                    break
            elif isinstance(short, str):
                assistant_message = {"role": "assistant", "content": short}
                history.append(assistant_message)
                MEMORY.append_history(assistant_message)
                print(f"[Agent回答]: {short}\n")
                break

            response = call_llm(
                [{"role": "system", "content": turn_ctx.get("system_prompt", build_system_prompt())}] + history,
                tools,
            )
            if response is None:
                # 调用彻底失败：错误信息已打印，保留用户消息，回到输入提示符继续会话
                break
            message = response.choices[0].message
            turn_ctx.update({"message": message, "usage": getattr(response, "usage", None)})
            HOOKS.emit("after_turn", turn_ctx)

            assistant_message = assistant_to_dict(message)
            history.append(assistant_message)
            MEMORY.append_history(assistant_message)

            if not message.tool_calls:
                reply = message.content or ""
                # ---- Stop 质量门禁（对应 Claude Code Stop Hook） ----
                stop_ctx = {
                    "reply": reply,
                    "history": history,
                    "todos": todos_mod.TODOS,
                    "retry": stop_gate_retries,
                }
                gate = HOOKS.emit("on_stop", stop_ctx)
                if isinstance(gate, HookDecision) and gate.is_blocking and stop_gate_retries < 1:
                    print(f"[hook:stop_quality_gate] {gate.reason}")
                    reminder_message = {
                        "role": "user",
                        "content": (
                            "Stop Hook 阻止本轮结束："
                            + gate.reason
                            + "\n请继续完成未完成的步骤。若确实无法继续，请说明原因。"
                        ),
                    }
                    history.append(reminder_message)
                    MEMORY.append_history(reminder_message)
                    stop_gate_retries += 1
                    continue
                reply = stop_ctx.get("reply", reply)
                # ---- 打印回答 ----（流式模式下内容已实时上屏并换行，不再重复打印）
                if not getattr(response, "streamed", False):
                    print(f"[Agent回答]: {reply}\n")
                # ---- 记忆压缩：history 超阈值时把旧消息沉淀进记忆文件 ----
                history = memory_compact.compact_history(history, client, MODEL, MEMORY)
                if todos_mod.TODOS:
                    unfinished = [t for t in todos_mod.TODOS if t["status"] != "completed"]
                    if unfinished:
                        print("[计划尚未办妥，Stop Hook 已提醒一次，暂不继续自动追问...]")
                        print(todos_mod.render_todos(todos_mod.TODOS))
                        print()
                        break
                    print("[最终计划状态 - 全部办妥]")
                    print(todos_mod.render_todos(todos_mod.TODOS))
                    print()
                    todos_mod.clear_todos()
                break

            # 将 tool_calls 适配成 {id, name, input}，再拆分为普通工具 vs dispatch_subagent
            tool_blocks = [to_tool_call(tc) for tc in message.tool_calls]
            dispatch_blocks = [b for b in tool_blocks if b.name == "dispatch_subagent"]
            other_blocks   = [b for b in tool_blocks if b.name != "dispatch_subagent"]

            results_map: dict[str, str] = {}

            # 普通工具顺序执行。统一经过 HookRegistry。
            for block in other_blocks:
                results_map[block.id] = execute_main_tool(block)

            # dispatch_subagent：多个时并发，单个时直接运行
            if len(dispatch_blocks) > 1:
                print(f"\n[并发派遣 {len(dispatch_blocks)} 个小太监...]\n")

                def _run_one(block):
                    return block.id, run_subagent(
                        task=block.input["task"],
                        agent_type=block.input.get("agent_type", "neiguan_yingzao"),
                        purpose=block.input.get("purpose", ""),
                    )

                with ThreadPoolExecutor(max_workers=len(dispatch_blocks)) as pool:
                    for block_id, summary in pool.map(_run_one, dispatch_blocks):
                        print(f"[主上下文压缩]: 子代理仅向主 history 追加 {len(summary)} 字\n")
                        results_map[block_id] = summary
            else:
                for block in dispatch_blocks:
                    summary = run_subagent(
                        task=block.input["task"],
                        agent_type=block.input.get("agent_type", "neiguan_yingzao"),
                        purpose=block.input.get("purpose", ""),
                    )
                    print(f"[主上下文压缩]: 子代理仅向主 history 追加 {len(summary)} 字\n")
                    results_map[block.id] = summary

            # 按原始顺序把每个工具结果作为一条 role="tool" 消息回传（OpenAI 协议要求）
            for b in tool_blocks:
                tool_message = {
                    "role": "tool",
                    "tool_call_id": b.id,
                    "content": results_map[b.id],
                }
                history.append(tool_message)
                MEMORY.append_history(tool_message)

            blocking_results = [
                results_map[b.id] for b in tool_blocks
                if isinstance(results_map.get(b.id), str) and is_blocking_tool_result(results_map[b.id])
            ]
            if blocking_results:
                reply = "奉天承运皇帝诏曰：工具请求被运行时策略拦截，未继续改写或换路径执行。\n\n" + blocking_results[0]
                assistant_message = {"role": "assistant", "content": reply}
                history.append(assistant_message)
                MEMORY.append_history(assistant_message)
                print(f"[Agent回答]: {reply}\n")
                break


if __name__ == "__main__":
    main()
