"""工具注册表（任务 4.1）：schema 与执行器绑定注册，name → ToolSpec 映射。

此前工具 schema 散落在 main.py（多个内联 schema）、tools.py（TOOL_SCHEMAS）和
team.py（重复的 list_mcp_servers），执行分发是 execute_main_tool 的 if/elif 长链
和 TeammateManager._exec 各自为政。注册表化之后：

- 新增工具 = 在本模块 register_tool() 一条记录（schema + handler），全端立即可用
  （开放封闭原则：对新增工具开放，对分发逻辑封闭）；
- 主循环与队友线程从同一张表取 schema 和执行器，消灭两处维护；
- MCP 动态工具仍由 build_tool_schemas 按 connect 结果追加，execute_tool 里兜底直查。

handler 统一签名：(inp: dict, sender: str, prefix: str) -> str
- sender：消息类工具需要知道"以谁的名义"发（主 Agent 是 lead，队友是自己名字）；
- prefix：基础工具的终端打印前缀，用于区分 主/子/队友 的执行现场。
"""
from __future__ import annotations

import datetime
import json
import time
from types import SimpleNamespace

from . import todos as todos_mod
from .hooks import HOOKS, HookDecision, is_blocking_message
from .memory import MEMORY
from .mcp_client import MCP_TOOL_MAP, list_mcp_servers
from .subagent import SUBAGENT_TYPE_OPTIONS, run_subagent
from .team import BUS, TEAM, VALID_MSG_TYPES
from .tools import TOOL_SCHEMAS, execute_basic_tool


class ToolSpec:
    """一个工具 = 名字 + schema（给模型看）+ handler（真正执行）。"""

    def __init__(self, name: str, schema: dict, handler):
        self.name = name
        self.schema = schema
        self.handler = handler


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(name: str, schema: dict, handler) -> None:
    TOOL_REGISTRY[name] = ToolSpec(name, schema, handler)


def get_schemas(names: list[str] | None = None) -> list[dict]:
    """按名字取 schema 列表；names=None 取全部。MCP 动态工具由 build_tool_schemas 追加。"""
    keys = names if names is not None else list(TOOL_REGISTRY)
    return [TOOL_REGISTRY[n].schema for n in keys if n in TOOL_REGISTRY]


def execute_tool(name: str, inp: dict, sender: str = "lead", prefix: str = "") -> str:
    """统一执行入口：先查注册表，未注册的再查 MCP 动态工具表，都没有则报未知工具。"""
    spec = TOOL_REGISTRY.get(name)
    if spec is not None:
        return spec.handler(inp, sender=sender, prefix=prefix)
    if name in MCP_TOOL_MAP:
        mcp_client, tool = MCP_TOOL_MAP[name]
        return mcp_client.call_tool(tool.name, inp)
    return f"Error: Unknown tool '{name}'"


def _emit_event(on_event, event: dict) -> None:
    """订阅者异常绝不能影响内核（与 runner._emit_to 同款语义）。"""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        pass


def execute_guarded(name: str, inp: dict, sender: str = "lead", prefix: str = "",
                    *, on_event=None, confirmer=None) -> str:
    """统一守卫执行入口（阶段十）：Hook 链 + 工具执行，三端（主循环/子代理/队友）共用。

    - confirmer：ask 决策的确认回调（接收 HookDecision，返回 bool）。传 None 表示该执行体
      无法请求用户确认（子代理/队友）——ask 按 fail-closed 降级为拒绝，与终端非交互环境
      的默认拒绝语义一致（hooks.confirm_hook_decision）。
    - on_event：可选事件订阅者。主循环传 runner 的 _emit，界面事件（tool_start/tool_end/
      hook_ask/hook_decision）由本入口发出，字段与收编前 dispatch_tool 逐字段一致；
      子代理/队友不传则零事件，其执行现场仍由内层 execute_basic_tool 的打印呈现。
    - 时序契约：hook_ask 事件先于 confirmer 调用发出（web/server.py 的 WSConfirmer
      依赖此序——"dispatch_tool 在调用前已发出 hook_ask 事件，这里只负责等"）。
    """
    tool_ctx: dict = {"name": name, "input": inp, "sender": sender}
    decision = HOOKS.emit("before_tool_call", tool_ctx, tool_matcher=name)
    if isinstance(decision, HookDecision):
        if decision.is_blocking:
            _emit_event(on_event, {"type": "hook_decision", "action": decision.action,
                                   "reason": decision.reason})
            return decision.to_message()
        if decision.action == "ask":
            # E4.1 同款：结构化携带工具名与完整参数（reason 里的命令被 Hook 截断至 120 字符，
            # 用户"看清再批"需要完整原文；input 取 tool_ctx——已含先前 allow hook 的改写）
            _emit_event(on_event, {
                "type": "hook_ask", "reason": decision.reason,
                "tool": tool_ctx.get("name", name),
                "input": tool_ctx.get("input", inp),
                "level": getattr(decision, "level", "") or "",
            })
            allowed = bool(confirmer(decision)) if confirmer is not None else False
            if not allowed:
                if confirmer is not None:
                    denied_reason = f"用户未确认高敏感操作：{decision.reason}"
                else:
                    denied_reason = (f"当前执行体无法请求用户确认（fail-closed），已默认拒绝："
                                     f"{decision.reason}")
                denied = HookDecision(action="deny", reason=denied_reason)
                _emit_event(on_event, {"type": "hook_decision", "action": "deny",
                                       "reason": denied.reason})
                return denied.to_message()
            _emit_event(on_event, {"type": "hook_decision", "action": "allow", "reason": "用户已确认"})
    elif isinstance(decision, str):
        return decision

    inp = tool_ctx.get("input", inp)
    _emit_event(on_event, {"type": "tool_start", "name": name, "input": inp})
    start = time.perf_counter()
    output = execute_tool(name, inp, sender=sender, prefix=prefix)

    if tool_ctx.get("_hook_updated_reason") and isinstance(output, str):
        output += ("\n[运行时提示] " + tool_ctx["_hook_updated_reason"]
                   + "。请以实际执行参数为准，不要再尝试写回原路径。")

    tool_ctx.update({
        "name": name, "input": inp, "output": output,
        "duration_ms": (time.perf_counter() - start) * 1000,
    })
    HOOKS.emit("after_tool_call", tool_ctx, tool_matcher=name)
    output = tool_ctx.get("output", output)

    output_text = str(output)
    _emit_event(on_event, {
        "type": "tool_end", "name": name, "output": output_text[:300],
        "blocked": is_blocking_message(output_text),
        # 成败沿子代理同款约定（"Error" 开头计为失败，宁漏勿误判）
        "ok": not is_blocking_message(output_text) and not output_text.startswith("Error"),
        "duration_ms": round(tool_ctx.get("duration_ms", 0), 1),
    })
    return output


# ============== 基础工具：schema 复用 tools.TOO_SCHEMAS，handler 统一转发 ==============
def _basic_handler(tool_name: str):
    def handler(inp: dict, sender: str = "lead", prefix: str = "") -> str:
        return execute_basic_tool(SimpleNamespace(name=tool_name, input=inp), prefix=prefix)
    return handler


for _name, _schema in TOOL_SCHEMAS.items():
    register_tool(_name, _schema, _basic_handler(_name))


# ============== 高层工具：schema 与 handler 在此一一对应 ==============
def _send_message(inp: dict, sender: str = "lead", prefix: str = "") -> str:
    return BUS.send(sender, inp["to"], inp["content"], inp.get("msg_type", "message"))


def _read_inbox(inp: dict, sender: str = "lead", prefix: str = "") -> str:
    return json.dumps(BUS.read_inbox(sender), ensure_ascii=False, indent=2)


def _broadcast(inp: dict, sender: str = "lead", prefix: str = "") -> str:
    return BUS.broadcast(sender, inp["content"], TEAM.member_names())


def _dispatch_subagent(inp: dict, sender: str = "lead", prefix: str = "") -> str:
    # 主循环会对多个 dispatch_subagent 并发调度，不经此路径；此 handler 保证
    # 单独调用时行为正确（顺序执行），语义一致。
    return run_subagent(
        task=inp["task"],
        agent_type=inp.get("agent_type", "neiguan_yingzao"),
        purpose=inp.get("purpose", ""),
    )


register_tool(
    "list_mcp_servers",
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
    lambda inp, sender="lead", prefix="": list_mcp_servers(inp.get("server")),
)

register_tool(
    "update_todos",
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
    lambda inp, sender="lead", prefix="": todos_mod.update_todos(inp.get("todos", [])),
)

register_tool(
    "dispatch_subagent",
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
    _dispatch_subagent,
)

register_tool(
    "spawn_teammate",
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
    lambda inp, sender="lead", prefix="": TEAM.spawn(inp["name"], inp["role"], inp["prompt"]),
)

register_tool(
    "list_teammates",
    {
        "type": "function",
        "function": {
            "name": "list_teammates",
            "description": "列出 agent team 中所有队友的名字、职司和状态。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    lambda inp, sender="lead", prefix="": TEAM.list_all(),
)

register_tool(
    "send_message",
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
    _send_message,
)

register_tool(
    "read_inbox",
    {
        "type": "function",
        "function": {
            "name": "read_inbox",
            "description": "读取并清空自己（lead 或队友）的 inbox。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    _read_inbox,
)

register_tool(
    "broadcast",
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
    _broadcast,
)

register_tool(
    "save_memory",
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "把值得长期记住的稳定事实写入记忆卷宗（用户偏好、背景、项目约定等）。"
                "用户说\"记住…\"\"以后请…\"时调用；寒暄与一次性细节不要记。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要记住的事实，一句简洁陈述句"}
                },
                "required": ["content"]
            }
        }
    },
    lambda inp, sender="lead", prefix="": MEMORY.append_memory(str(inp.get("content", ""))),
)

# ============== 演示工具（任务 4.1 完成标志的活体证明） ==============
# 新增这个工具只写了下面一条注册记录，main.py / team.py 的分发代码零改动。
# 模型本身不知道"现在几点"，这个工具补上了时间感知。
register_tool(
    "current_time",
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "获取当前的本地日期和时间。回答'现在几点/今天几号'等时间问题前调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    lambda inp, sender="lead", prefix="": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
)
