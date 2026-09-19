#!/usr/bin/env python3
"""main.py — 终端入口（任务 A2 起为薄外壳）。

对话内核已抽至 agent_core/runner.py（SessionRunner：事件流 + confirmer 注入），
本文件只负责：读输入、斜杠命令、把内核事件渲染成终端输出。
Web 入口（web/server.py，A3 起）驱动同一个内核。
"""
from __future__ import annotations

import json

from agent_core import app_settings, todos as todos_mod
from agent_core.console import ensure_utf8_console
from agent_core.config import EXPORTS_DIR, MCP_CONFIG_PATH, PERSONA_DIR, PROJECT_ROOT
from agent_core.hooks import confirm_hook_decision
from agent_core.mcp_client import connect_all, list_mcp_servers
from agent_core.memory import MEMORY
from agent_core.runner import SessionRunner
from agent_core.sessions import SESSIONS
from agent_core.team import BUS, TEAM


def terminal_printer(event: dict) -> None:
    """把内核事件渲染成终端输出。

    只渲染对话流相关事件；工具/todos 更新/ask 等事件不打印——
    内层模块（execute_basic_tool、confirm_hook_decision、update_todos）已有自己的打印，
    重复渲染会破坏终端输出格式。WebSocket 订阅者（A3）则会全量转发。
    """
    t = event.get("type")
    if t == "reply_start":
        print("[Agent回答]: ", end="", flush=True)
    elif t == "token":
        print(event["text"], end="", flush=True)
    elif t == "reply_end":
        print("\n")
    elif t == "reply":
        print(f"[Agent回答]: {event['text']}\n")
    elif t == "retry" or t == "error":
        print(event["message"])
    elif t == "stop_gate":
        print(f"[hook:stop_quality_gate] {event['reason']}")
    elif t == "subagents_start":
        print(f"\n[并发派遣 {event['count']} 个小太监...]\n")
    elif t == "subagent_summary":
        print(f"[主上下文压缩]: 子代理仅向主 history 追加 {event['length']} 字\n")
    elif t == "todos" and event.get("note") == "unfinished":
        print("[计划尚未办妥，Stop Hook 已提醒一次，暂不继续自动追问...]")
        print(todos_mod.render_todos(event["todos"]))
        print()
    elif t == "todos" and event.get("note") == "all_done":
        print("[最终计划状态 - 全部办妥]")
        print(todos_mod.render_todos(event["todos"]))
        print()


def main():
    ensure_utf8_console()   # GBK 控制台 print emoji 会炸内核，入口处统一 UTF-8
    # 连接 MCP Server 并把外部工具并入 schema 表
    connect_all(MCP_CONFIG_PATH)

    print("累积式 Agent（tools + memory + skills + subagent + team + mcp + hooks）")
    print("输入 q/quit/exit 退出；/team 队友；/inbox 收件箱；/mcp 工具；/todos 计划；/memory 记忆；/compact 压缩；/new 新会话；/mi 密折（临时对话）；/resume 恢复会话；/find 检索会话；/export 誊出话本；/persona 人格；/settings 设置")
    runner = SessionRunner(on_event=terminal_printer, confirmer=confirm_hook_decision)
    print(f"当前会话：{runner.session_id}")

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
        if command == "/todos":
            print("===== 当前计划 =====")
            print(todos_mod.render_todos(todos_mod.TODOS))
            print()
            continue
        if command == "/memory":
            print("===== MEMORY.md（长期记忆）=====")
            print(MEMORY.read_memory().rstrip())
            print("===== USER.md（用户画像）=====")
            print(MEMORY.read_user().rstrip())
            print()
            continue
        if command == "/new":
            sid = runner.new_session()
            print(f"[新会话已开启] {sid}（旧会话可用 /resume 找回）\n")
            continue
        # 阶段十三：密折——临时对话（不入名册、不留记忆、退出即焚；/export 可手动誊出）
        if command in ("/mi", "/secret"):
            runner = SessionRunner(on_event=terminal_printer, confirmer=confirm_hook_decision,
                                   ephemeral=True)
            print(f"[密折开启] 会话 {runner.session_id}（不入名册 · 不留记忆 · 退出即焚）")
            print("  边界：工具照常受圣旨管控，审计日志照记；/export 手动誊出，/new /resume 转回正式殿。\n")
            continue
        # 注意带参数的命令要用前缀匹配：== "/resume" 在输入 "/resume <id>" 时永远不成立
        # （4.5 端到端实测踩坑：命令被当成聊天发给模型，模型自己翻文件"假装"恢复了）
        if command == "/resume" or command.startswith("/resume "):
            parts = command.split()
            if len(parts) < 2:
                print(SESSIONS.render_list())
                print()
                continue
            target = parts[1]
            if not SESSIONS.exists(target):
                print(f"[会话不存在] {target}")
                print(SESSIONS.render_list())
                print()
                continue
            count = runner.resume(target)
            print(f"[会话已恢复] {target}，共 {count} 条消息，可以继续对话\n")
            continue
        # 人格查看/切换（任务 4.6）；带参命令用前缀匹配（4.5 的教训）
        if command == "/persona" or command.startswith("/persona "):
            parts = command.split()
            available = sorted(p.stem for p in PERSONA_DIR.glob("*.md"))
            if len(parts) < 2:
                print(f"当前人格：{runner.persona}｜可用：{', '.join(available)}")
                print("切换：/persona <名字>（立即生效）；默认人格在 .env 设 AGENT_PERSONA=名字")
                print()
                continue
            target = parts[1]
            if target not in available:
                print(f"[未知人格] {target}｜可用：{', '.join(available)}")
                print()
                continue
            runner.switch_persona(target)
            print(f"[人格已切换] {target}（下一轮对话生效）\n")
            continue
        # 阶段九：查看内务府当前设置（修改走界面端"内务府"面板或直接编辑 settings.json）
        if command == "/settings":
            s = app_settings.load()
            print(f"===== 内务府设置 =====")
            print(f"圣旨批阅时限：{s['ask_timeout']:.0f} 秒｜默认人格：{s['default_persona'] or '(内核默认)'}｜出巡熔断预算：{s['subagent_fail_budget']} 次")
            print()
            continue
        if command == "/compact":
            before, after = runner.compact()
            if after < before:
                print(f"[手动压缩完成] history: {before} -> {after} 条，旧对话已沉淀进记忆文件")
            else:
                print(f"[无需压缩] 当前 history 共 {after} 条，没有可安全切分的旧对话段")
            print()
            continue
        # H1：会话检索（/resume 列表太长时按关键词缩小范围：题名 + 全文命中）
        if command == "/find" or command.startswith("/find "):
            parts = command.split(maxsplit=1)
            if len(parts) < 2:
                print("用法：/find <关键词>（在题名与对话内容中检索）\n")
                continue
            hits = SESSIONS.list_sessions(parts[1])
            if not hits:
                print(f"[未检索到] 没有偏殿匹配「{parts[1]}」\n")
                continue
            print(f"检索「{parts[1]}」命中 {len(hits)} 殿（新→旧，最多显示 15 个）：")
            for s in hits[:15]:
                print(f"  {s['id']}  [{s['mtime']}] {s['messages']}条  {s['preview']}")
            print("用 /resume <会话ID> 恢复继续。\n")
            continue
        # H2：整卷导出为 Markdown 话本（exports/ 目录下，文件名 = 会话ID）
        if command == "/export" or command.startswith("/export "):
            parts = command.split()
            target = parts[1] if len(parts) > 1 else runner.session_id
            if runner.ephemeral and target == runner.session_id:
                # 阶段十三：密折誊出——从内存史渲染（逃生门，皇上钦定保留）
                md = SESSIONS.render_history_markdown(runner.history, target, "密折")
            else:
                md = SESSIONS.export_markdown(target)
            if md is None:
                print(f"[无法导出] 会话 {target} 尚无记录（传过旨才有话本可誊）")
                print()
                continue
            out_dir = EXPORTS_DIR
            out_dir.mkdir(exist_ok=True)
            out = out_dir / f"{target}.md"
            out.write_text(md, encoding="utf-8")
            print(f"[话本已誊出] {out}")
            print()
            continue

        try:
            runner.send(user_input)
        except Exception as exc:  # 阶段十一（终端护栏）：内核意外不崩进程，与 Web 线程兜底同级
            print(f"\n[内核异常，本轮已收束，会话可继续] {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
