"""Hooks：生命周期拦截、注入与审计。

四层 Hook 模型：Event（事件）→ Matcher（匹配器）→ Handler（处理器）→ Decision（决策）。
该模型与 Claude Code 官方的 Event → Matcher → Handler → Output 结构完全对齐。
Claude Code 官方支持五种 Handler 类型：command / http / mcp_tool / prompt / agent。
教学版统一用 Python 类方法，但保留了相同的四层结构和决策语义。
"""
from __future__ import annotations

import datetime
import json
import sys
import time
from typing import Any

from . import todos as _todos
from .config import AUDIT_FILE


class HookDecision:
    """Hook 的结构化决策结果。与 Claude Code 的 permissionDecision 概念对齐。

    教学版支持四种决策：
    - allow：放行（可附带 updated_input 改写工具参数）
    - deny：拒绝（工具不执行，reason 会反馈给 Agent）
    - ask：请求用户确认（拒绝或非交互环境默认不执行工具）
    - block：阻止并给出原因（等同于 Claude Code 的继续处理指令）
    """

    def __init__(self, action: str, reason: str = "", updated_input: dict[str, Any] | None = None):
        self.action = action            # "allow" | "deny" | "ask" | "block"
        self.reason = reason            # 人类可读原因
        self.updated_input = updated_input  # 可选：改写工具参数（对应 Claude Code 的 updatedInput）

    @property
    def is_blocking(self) -> bool:
        """是否阻止当前操作继续执行。"""
        return self.action in ("deny", "block")

    def to_message(self) -> str:
        """转为 Agent 可读的反馈消息。"""
        prefix = {"deny": "拒绝", "block": "阻止", "ask": "需要确认", "allow": "已放行"}
        label = prefix.get(self.action, self.action)
        msg = f"[HookDecision: {label}] {self.reason}"
        if self.updated_input:
            msg += f"（参数已改写：{list(self.updated_input.keys())}）"
        return msg


def confirm_hook_decision(decision: HookDecision) -> bool:
    """处理 ask 决策。

    教学版故意保持同步确认：终端里输入 y 才继续；非交互环境默认拒绝。
    这更接近权限 Hook 的 fail-closed 行为。
    """
    print(f"\n[hook:permission] {decision.reason}")
    if not sys.stdin.isatty():
        print("[hook:permission] 当前不是交互式终端，默认拒绝执行。\n")
        return False
    try:
        answer = input("[hook:permission] 是否继续执行？输入 y 继续，其余取消: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


class Hook:
    """Hook 基类：所有事件默认空实现。

    四层模型说明（教学版 → Claude Code 官方映射）：
    - Event（事件）：方法名即事件，如 before_turn、before_tool_call、on_stop
    - Matcher（匹配器）：matcher 属性控制对哪些工具触发，如 "write_file"、"run_command"
    - Handler（处理器）：子类覆写事件方法实现具体逻辑。Claude Code 支持 command/http/mcp/prompt/agent 五种
    - Decision（决策）：返回 HookDecision 或字符串来放行/拒绝/确认/阻止
    """

    name: str = ""
    matcher: str = "*"  # 工具名匹配："*"=所有、"Edit|Write"=写入、"run_command"=命令

    def matches(self, tool_name: str | None) -> bool:
        """检查此 Hook 是否匹配给定工具名。对应 Claude Code 的 matcher 字段。

        支持格式：
        - "*" 或 ""：匹配所有工具
        - "Edit|Write" 或 "Edit, Write"：管道/逗号分隔，匹配任一
        - "run_command"：精确匹配
        """
        if not tool_name or self.matcher in ("*", ""):
            return True
        patterns = [p.strip() for p in self.matcher.replace(",", "|").split("|")]
        return tool_name in patterns

    # ---- 基础事件 ----
    def before_turn(self, ctx: dict[str, Any]) -> Any:
        """LLM 调用前触发。可修改 ctx["system_prompt"]，返回非 None 则短路。"""
        pass

    def after_turn(self, ctx: dict[str, Any]) -> Any:
        """LLM 调用后触发。ctx 含 message、usage，用于日志/统计。"""
        pass

    def before_tool_call(self, ctx: dict[str, Any]) -> Any:
        """工具执行前触发。可拒绝、改写参数、请求确认。"""
        pass

    def after_tool_call(self, ctx: dict[str, Any]) -> Any:
        """工具执行后触发。可观察输出、截断、注入 feedback。"""
        pass

    def on_user_input(self, ctx: dict[str, Any]) -> Any:
        """用户提交输入时触发。"""
        pass

    # ---- s12 增强事件（对应 Claude Code 官方的 Stop / SessionStart） ----
    def on_stop(self, ctx: dict[str, Any]) -> Any:
        """Agent 准备结束本轮回答时触发。对应 Claude Code 的 Stop 事件。
        可返回 HookDecision(action="block") 让 Agent 继续处理未完成的工作。"""
        pass

    def on_session_start(self, ctx: dict[str, Any]) -> Any:
        """会话启动或恢复时触发。对应 Claude Code 的 SessionStart。
        适合注入动态上下文、环境变量、当前分支等运行时信息。"""
        pass


class HookRegistry:
    """管理 hook 链并按注册顺序触发事件。

    核心规则：
    1. 按注册顺序执行：先注册的 hook 先收到事件
    2. Matcher 过滤：before/after_tool_call 事件按 Hook.matcher 过滤
    3. 短路：任一 hook 返回非 None 值（非 allow 类的 HookDecision），立即中断
    4. 错误隔离：单个 hook 异常不影响其他 hook，打印 [hook error] 后继续
    """

    def __init__(self):
        self._hooks: list[Hook] = []

    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)

    def emit(self, event: str, ctx: dict[str, Any] | None = None,
             tool_matcher: str | None = None) -> Any:
        """触发事件，按顺序通知所有 hook。

        tool_matcher: 当前工具名（before/after_tool_call 事件传入），用于 matcher 过滤
        """
        ctx = {} if ctx is None else ctx
        for hook in self._hooks:
            # ---- Matcher 过滤：工具级事件按 matcher 过滤 ----
            if tool_matcher and event in ("before_tool_call", "after_tool_call"):
                if not hook.matches(tool_matcher):
                    continue

            method = getattr(hook, event, None)
            if method is None:
                continue
            try:
                result = method(ctx)
                if result is not None:
                    # ---- 处理 HookDecision ----
                    if isinstance(result, HookDecision):
                        if result.action == "allow":
                            # allow 不短路，继续执行后续 hook
                            if result.updated_input:
                                ctx["input"] = result.updated_input
                                ctx["_hook_updated_input"] = result.updated_input
                                ctx["_hook_updated_reason"] = result.reason
                            continue
                        # deny/ask/block：短路返回
                        return result
                    # 字符串或其他非 None：短路返回（兼容旧行为）
                    return result
            except Exception as exc:
                print(f"[hook error] {event} in {hook.name or hook.__class__.__name__}: {exc}")
        return None


class LoggingHook(Hook):
    """After Hook 示例：打印每轮 LLM 调用耗时与 token。"""

    name = "logging"

    def before_turn(self, ctx):
        ctx["_start"] = time.perf_counter()

    def after_turn(self, ctx):
        start = ctx.get("_start")
        if start is None:
            return
        duration_ms = (time.perf_counter() - start) * 1000
        usage = ctx.get("usage")
        if usage:
            print(
                f"[hook:logging] turn finished in {duration_ms:.1f}ms | "
                f"input={getattr(usage, 'input_tokens', '?')} output={getattr(usage, 'output_tokens', '?')}"
            )
        else:
            print(f"[hook:logging] turn finished in {duration_ms:.1f}ms")


class ToolAuditHook(Hook):
    """After Hook 示例：把写类和命令类工具调用记录到 JSONL。

    matcher 设为 "write_file|run_command"，由 HookRegistry 自动过滤，
    不再需要在方法内手动判断工具名。"""

    name = "tool_audit"
    matcher = "write_file|run_command"

    def after_tool_call(self, ctx):
        name = ctx.get("name", "")
        entry = {
            "ts": datetime.datetime.now().isoformat(),
            "tool": name,
            "input": ctx.get("input"),
        }
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[hook:tool_audit] {name} 已审计到 {AUDIT_FILE}")


class ToolPolicyHook(Hook):
    """Before Hook 示例：统一处理工具调用前的策略。

    一个 Hook 覆盖教学里最有代表性的 before_tool_call 能力：
    - allow + updated_input：把演示生产路径改写到沙箱
    - deny：拒绝敏感文件写入和破坏性命令
    - ask：高敏感操作交给用户确认
    """

    name = "tool_policy"
    matcher = "write_file|run_command"

    SENSITIVE_PATTERNS = [
        ".env",
        ".env.local",
        ".env.production",
        "credentials.json",
        "id_rsa",
        "id_ed25519",
        ".ssh/",
        "production.yml",
        "production.yaml",
        "secrets/",
        ".aws/credentials",
    ]

    DANGEROUS_PATTERNS = [
        ("rm -rf /", "递归删除根目录"),
        ("rm -rf ~", "递归删除用户目录"),
        ("DROP TABLE", "删除数据库表"),
        ("DROP DATABASE", "删除数据库"),
        ("mkfs.", "格式化文件系统"),
        ("dd if=", "直接磁盘写入"),
        ("> /dev/sda", "覆写磁盘设备"),
        ("chmod 777 /", "开放根目录权限"),
        (":(){ :|:& };:", "fork bomb"),
    ]

    HIGH_SENSITIVITY = [
        ("git push", "推送到远程仓库"),
        ("git commit", "提交代码变更"),
        ("npm publish", "发布 npm 包"),
        ("pip install", "安装 Python 依赖"),
        ("docker build", "构建 Docker 镜像"),
        ("docker push", "推送 Docker 镜像"),
        ("kubectl apply", "应用 Kubernetes 配置"),
        ("terraform apply", "执行 Terraform 变更"),
    ]

    source_prefix = "demo_production/"
    target_prefix = "sandbox/demo_production/"

    def _normalize_path(self, path: str) -> str:
        normalized = str(path).strip().replace("\\", "/")
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    def _match_pattern(self, value: str, patterns) -> tuple[str, str] | None:
        for item in patterns:
            pattern, description = item if isinstance(item, tuple) else (item, item)
            if pattern in value:
                return pattern, description
        return None

    def _rewrite_path_prefix(self, path: str, source_prefix: str, target_prefix: str) -> str | None:
        normalized = self._normalize_path(path)
        if normalized.startswith(source_prefix):
            return target_prefix + normalized[len(source_prefix):]
        return None

    def before_tool_call(self, ctx):
        inp = ctx.get("input", {}) or {}
        if ctx.get("name") == "run_command":
            command = inp.get("command", "")

            dangerous = self._match_pattern(command, self.DANGEROUS_PATTERNS)
            if dangerous:
                pattern, description = dangerous
                reason = f"危险命令已拦截：{description}（匹配模式：{pattern}）"
                print(f"[hook:tool_policy] {reason}")
                return HookDecision(action="deny", reason=reason)

            high_sensitivity = self._match_pattern(command, self.HIGH_SENSITIVITY)
            if high_sensitivity:
                _, description = high_sensitivity
                return HookDecision(
                    action="ask",
                    reason=f"需要确认：{description}。命令：{command[:120]}",
                )
            return

        updated_input = None
        raw_path = str(inp.get("path", ""))
        path = self._normalize_path(raw_path)
        new_path = self._rewrite_path_prefix(path, self.source_prefix, self.target_prefix)
        if new_path:
            updated_input = dict(inp)
            updated_input["path"] = new_path
            path = new_path
            print(f"[hook:tool_policy] 写入路径已改写：{raw_path} -> {new_path}")

        sensitive = self._match_pattern(path, self.SENSITIVE_PATTERNS)
        if sensitive:
            pattern, _ = sensitive
            reason = f"敏感文件写入已拦截：'{path}'（匹配模式：{pattern}）"
            print(f"[hook:tool_policy] {reason}")
            return HookDecision(action="deny", reason=reason)

        if updated_input:
            return HookDecision(
                action="allow",
                reason=f"写入路径已改写到沙箱：{updated_input['path']}",
                updated_input=updated_input,
            )


class OutputFormattingHook(Hook):
    """After Hook 示例：截断过长工具输出，防止上下文污染。

    展示 After Hook 的输出改写能力。对应 Claude Code 中通过 additionalContext
    或 updatedToolOutput 向模型反馈处理后的结果。"""

    name = "output_format"
    matcher = "*"  # 匹配所有工具

    def __init__(self, max_output_chars: int = 4000):
        self.max_output_chars = max_output_chars

    def after_tool_call(self, ctx):
        output = ctx.get("output", "")
        if isinstance(output, str) and len(output) > self.max_output_chars:
            truncated = (
                output[:self.max_output_chars]
                + f"\n\n[... 输出已截断，原始共 {len(output)} 字符，"
                + f"显示前 {self.max_output_chars} 字符]"
            )
            ctx["output"] = truncated
            ctx["_truncated"] = True
            print(
                f"[hook:output_format] 输出截断：原始 {len(output)} -> "
                f"{self.max_output_chars} 字符"
            )


class StopQualityGateHook(Hook):
    """质量门禁 Hook：在 Agent 准备结束本轮回答时进行基本检查。

    展示 on_stop 事件和 "block" 决策。对应 Claude Code 的 Stop 事件质量门禁模式。"""

    name = "stop_quality_gate"

    def on_stop(self, ctx):
        reply = ctx.get("reply", "")
        if ctx.get("retry", 0) >= 1:
            return

        # 检查回答是否过短（可能是模型截断）
        if reply and len(reply.strip()) < 10:
            return HookDecision(
                action="block",
                reason="回答似乎不完整（少于10个字符），请检查并重新生成更完整的回复。",
            )

        # 检查是否有未完成的待办事项——注入提醒上下文
        todos = ctx.get("todos", _todos.TODOS)
        unfinished = [t for t in todos if t["status"] != "completed"]
        if unfinished:
            ctx["_has_unfinished_todos"] = True
            return HookDecision(
                action="block",
                reason="仍有未完成待办，Stop Hook 要求继续执行。",
            )


HOOKS = HookRegistry()
HOOKS.register(LoggingHook())
HOOKS.register(ToolPolicyHook())
HOOKS.register(ToolAuditHook())
HOOKS.register(OutputFormattingHook(max_output_chars=4000))
HOOKS.register(StopQualityGateHook())
