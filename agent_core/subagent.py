"""子代理：独立 message loop 的临时派差，办完只回传总结，不污染主上下文。"""
from __future__ import annotations

import os

from .llm import MODEL, assistant_to_dict, client, to_tool_call
from .tools import TOOL_SCHEMAS, execute_basic_tool

# 任务 5.1：失败预算（熔断）。oxalpha 事件里子代理在网络不可达时傻傻烧满全部回合，
# 只回传一句无原因的固定失败串。现在连续 N 次工具失败即提前收兵，并回传原因与统计。
# 阈值用"连续"而非"累计"：累计会把"多次失败后成功"的健康探索也误杀。
FAIL_BUDGET = int(os.environ.get("AGENT_SUBAGENT_FAIL_BUDGET", "3"))


def _is_tool_failure(content: str) -> bool:
    """工具结果是否计为失败。

    约定：web_fetch 的失败（超时/DNS/SSRF）与 run_command 的超时都以 "Error" 开头；
    普通命令的非零退出返回的是 stderr 原文，无法可靠识别，按成功计（宁漏勿误杀）。
    """
    return content.startswith("Error")


def _circuit_breaker_message(consecutive: int, turns_used: int) -> str:
    return (
        f"（子代理提前收兵：连续 {consecutive} 次工具调用失败，疑似网络不可达或资源受限；"
        f"已尝试 {turns_used} 轮。建议：确认网络/代理是否可用，或改派本地只读任务。）"
    )


def _max_turns_message(turns: int, ok: int, fail: int) -> str:
    return (
        f"（子代理达到 {turns} 轮上限未办妥；期间工具调用 {ok} 次成功、{fail} 次失败。"
        f"若失败居多，多半是目标不可达，建议换任务口径或确认网络。）"
    )


# ============== 子代理预设身份 ==============
# 身份在 system_prompt 中定义，工具白名单在代码中控制（不放进 prompt）。
# 这里故意使用宫廷内官职位做角色名：既贴合教程人设，也让不同子代理的职责边界更好记。
def build_subagent_prompt(title: str, duty: str, boundary: str) -> str:
    return (
        f"你是{title}，奉总管之命专办一件差事。\n"
        f"- 职司：{duty}\n"
        f"- 边界：{boundary}\n"
        "- 不必使用\"奉天承运皇帝诏曰\"前缀，那是总管对皇上的礼数。\n"
        "- 用工具尽快把差事办妥，最后用一段简短中文向总管回禀结果。\n"
        "- 只回禀结论与关键信息，不要复述每一步细节。\n"
        "- 你不能再派遣其他小太监，所有差事自己跑工具完成。"
    )


SUBAGENT_SPECS = {
    # 小黄门：宫中通传、跑腿的小内侍。适合短平快的只读探路。
    "xiaohuangmen": {
        "title": "通传小黄门",
        "system_prompt": build_subagent_prompt(
            "通传小黄门",
            "传话跑腿、快速探路、确认简单事实。",
            "只办轻量只读差事；若发现需要大改或长时间探索，回禀总管改派专职内官。",
        ),
        "tools": ["run_command", "read_file", "glob", "grep"],
        "max_turns": 8,
    },
    # 司礼监掌文书机要，这里取“随堂”做文书型子代理。
    "sili_suitang": {
        "title": "司礼监随堂小太监",
        "system_prompt": build_subagent_prompt(
            "司礼监随堂小太监",
            "查阅文书、阅读代码、整理提纲、归纳结论。",
            "只读不写；不得修改文件，只把文书脉络和关键判断回禀总管。",
        ),
        "tools": ["load_skill", "read_file", "glob", "grep"],
        "max_turns": 12,
    },
    # 东厂负责查访缉事，这里用于外部网页、搜索、探索性调查。
    "dongchang_tanshi": {
        "title": "东厂探事小太监",
        "system_prompt": build_subagent_prompt(
            "东厂探事小太监",
            "外出查访、抓取网页、搜罗线索、比对资料来源。",
            "只读不写；运行命令时只许做查询类操作，不得改动本地文件。",
        ),
        "tools": ["run_command", "web_fetch", "load_skill", "read_file", "glob", "grep"],
        "max_turns": 15,
    },
    # 尚宝监掌印信宝册，这里用于盘点、校验、对账。
    "shangbao_dianbu": {
        "title": "尚宝监典簿小太监",
        "system_prompt": build_subagent_prompt(
            "尚宝监典簿小太监",
            "清点文件、核对清单、校验结果、整理表册。",
            "只读不写；重点回禀差异、遗漏、风险点和可复核证据。",
        ),
        "tools": ["run_command", "read_file", "glob", "grep"],
        "max_turns": 12,
    },
    # 内官监掌宫中营造器用，这里用于真正动手改文件、落地实现。
    "neiguan_yingzao": {
        "title": "内官监营造小太监",
        "system_prompt": build_subagent_prompt(
            "内官监营造小太监",
            "修造工程、改写文件、搭建目录、跑命令验收。",
            "可读写可执行；动手前先看清现状，回禀时列出改了什么和验证结果。",
        ),
        "tools": ["run_command", "web_fetch", "load_skill", "read_file", "write_file", "glob", "grep"],
        "max_turns": 20,
    },
}

SUBAGENT_TYPE_OPTIONS = list(SUBAGENT_SPECS.keys())


def resolve_subagent_type(agent_type: str) -> str:
    normalized = (agent_type or "neiguan_yingzao").strip()
    if normalized not in SUBAGENT_SPECS:
        return "neiguan_yingzao"
    return normalized


_SUBAGENT_COUNTER = 0


def run_subagent(task: str, agent_type: str = "neiguan_yingzao",
                 purpose: str = "", max_turns: int | None = None) -> str:
    """启动一个独立 message loop 的子代理，跑完后只返回最终文本给主 agent。

    agent_type: SUBAGENT_SPECS 中的宫廷职位名。
    """
    global _SUBAGENT_COUNTER
    _SUBAGENT_COUNTER += 1
    label = purpose or task[:40]

    agent_type = resolve_subagent_type(agent_type)
    spec = SUBAGENT_SPECS[agent_type]
    turns = max_turns if max_turns is not None else spec["max_turns"]
    tools = [TOOL_SCHEMAS[t] for t in spec["tools"]]

    print(f"\n[派遣小太监 #{_SUBAGENT_COUNTER}({spec['title']} / {agent_type})]: {label}")
    print("  ┌── subagent context start ──")

    messages = [{"role": "user", "content": task}]
    consecutive_failures = 0
    ok_count = 0
    fail_count = 0

    for turn in range(turns):
        msg = client.chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            messages=[{"role": "system", "content": spec["system_prompt"]}] + messages,
            tools=tools,
        ).choices[0].message
        messages.append(assistant_to_dict(msg))

        if not msg.tool_calls:
            final = msg.content or ""
            print(f"  └── subagent context end (内部 {turn + 1} 轮，回传 {len(final)} 字) ──")
            print(f"[小太监回禀]: {final}\n")
            return final

        for tc in msg.tool_calls:
            block = to_tool_call(tc)
            content = execute_basic_tool(block, prefix=f"子({spec['title']})·")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            })
            if _is_tool_failure(content):
                consecutive_failures += 1
                fail_count += 1
            else:
                consecutive_failures = 0
                ok_count += 1

        # 熔断检查放在整批工具执行完之后：协议要求每个 tool_call 都要有配对结果
        if consecutive_failures >= FAIL_BUDGET:
            text = _circuit_breaker_message(consecutive_failures, turn + 1)
            print(f"  └── 连续 {consecutive_failures} 次工具失败，触发熔断提前收兵（第 {turn + 1} 轮）──\n")
            print(f"[小太监回禀]: {text}\n")
            return text

    text = _max_turns_message(turns, ok_count, fail_count)
    print(f"  └── subagent context end (达到 {turns} 轮上限，成功 {ok_count} / 失败 {fail_count}) ──\n")
    print(f"[小太监回禀]: {text}\n")
    return text
