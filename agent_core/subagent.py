"""子代理：独立 message loop 的临时派差，办完只回传总结，不污染主上下文。"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from .config import SUBAGENT_LOG_DIR
from . import app_settings, llm
from .llm import MAX_LLM_RETRIES, RETRYABLE_ERRORS, assistant_to_dict, to_tool_call
from .tools import TOOL_SCHEMAS, hosts_loopback_domains

# 任务 5.1：失败预算（熔断）。oxalpha 事件里子代理在网络不可达时傻傻烧满全部回合，
# 只回传一句无原因的固定失败串。现在连续 N 次工具失败即提前收兵，并回传原因与统计。
# 阈值用"连续"而非"累计"：累计会把"多次失败后成功"的健康探索也误杀。
# 阶段九：预算走内务府设置（每次派遣现读，改完即生效），env 种子在 app_settings 里。


def _fail_budget() -> int:
    return app_settings.load()["subagent_fail_budget"]


def _is_tool_failure(content: str) -> bool:
    """工具结果是否计为失败。

    约定：web_fetch 的失败（超时/DNS/SSRF）与 run_command 的超时都以 "Error" 开头；
    普通命令的非零退出返回的是 stderr 原文，无法可靠识别，按成功计（宁漏勿误杀）。
    阶段十：Hook 链收编后子代理会收到策略拒绝消息（"[HookDecision: 拒绝/阻止]"开头）——
    被策略拦等于差事推进不了，同样计入连续失败，防止对着拒绝死循环烧回合。
    """
    return (content.startswith("Error")
            or content.startswith("[HookDecision: 拒绝]")
            or content.startswith("[HookDecision: 阻止]"))


def _circuit_breaker_message(consecutive: int, turns_used: int,
                             clues: list[str] | None = None) -> str:
    text = (
        f"（子代理提前收兵：连续 {consecutive} 次工具调用失败，疑似网络不可达或资源受限；"
        f"已尝试 {turns_used} 轮。"
    )
    if clues:
        text += "途中线索：" + " ｜ ".join(f"《{c}》" for c in clues) + "。"
    text += "建议：确认网络/代理是否可用，或改派本地只读任务。）"
    return text


def _max_turns_message(turns: int, ok: int, fail: int,
                       clues: list[str] | None = None) -> str:
    text = (
        f"（子代理达到 {turns} 轮上限未办妥；期间工具调用 {ok} 次成功、{fail} 次失败。"
    )
    if clues:
        # 阶段十五 15.3：超轮 ≠ 颗粒无收。线索附上让总管直接查收，不再第二遍重查
        text += "途中线索（请总管查收，可能已含答案）：" + " ｜ ".join(f"《{c}》" for c in clues) + "。"
    text += "若失败居多，多半是目标不可达，建议换任务口径或确认网络。）"
    return text


def _call_llm_with_retry(system_prompt: str, messages: list, tools: list) -> tuple:
    """子代理 LLM 调用兜底（阶段十四，债⑤）：瞬时错误指数退避重试，仍失败返回 (None, 原因)。

    降级为文字回禀而非抛异常：主循环拿到字符串照常走回禀流程，同批其他小太监的成果
    不受牵连；重试口径与主循环 call_llm 一致（RETRYABLE_ERRORS 迁 llm.py 共用）。
    """
    if llm.client is None:
        return None, "模型未配置（请在模型阁添加配置或检查 .env）"
    last = "未知错误"
    delay = 1.0
    for attempt in range(1, MAX_LLM_RETRIES + 1):
        try:
            resp = llm.client.chat.completions.create(
                model=llm.MODEL,
                max_tokens=2000,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=tools,
            )
            return resp.choices[0].message, ""
        except RETRYABLE_ERRORS as exc:
            last = f"{type(exc).__name__}: {str(exc)[:120]}"
            if attempt < MAX_LLM_RETRIES:
                time.sleep(delay)
                delay *= 2
        except Exception as exc:
            return None, f"{type(exc).__name__}: {str(exc)[:120]}"
    return None, last


def _llm_failure_message(reason: str, clues: list[str] | None = None) -> str:
    text = (
        f"（差事办砸：模型调用失败——{reason}，已重试 {MAX_LLM_RETRIES} 次未果。"
    )
    if clues:
        text += "途中线索：" + " ｜ ".join(f"《{c}》" for c in clues) + "。"
    text += "建议总管改派其他小太监、换口径重试，或稍后再办。）"
    return text


def _network_env_note(spec_tools: list[str]) -> str:
    """阶段十五 15.2 探子知情权：派遣前生成本机网络环境说明（无加速器 → 空串 → 零注入）。

    2026-09-21 查访事故：东厂探事不知道本机 hosts 式加速器的存在，web_fetch 被
    SSRF 防护连拦两轮（github.com 全被解析成 127.0.0.1）、curl 被 fail-closed
    拒绝，把轮次烧在撞墙上还不明所以。说明随差事注入，让奴才出门前先知路况。
    """
    if not ({"web_fetch", "run_command"} & set(spec_tools)):
        return ""  # 无网络工具的身份（如小黄门）用不上路况
    domains = hosts_loopback_domains()
    if not domains:
        return ""  # 本机无 hosts 式加速器：不注入，行为与旧版完全一致
    sample = "、".join(sorted(domains)[:8])
    more = f"等共 {len(domains)} 个域名" if len(domains) > 8 else "域名"
    return (
        f"[本机网络环境说明] 此机 hosts 将 {sample}{more}映射到本机回环（加速器特征），"
        "web_fetch 访问这些域名已放行可直连；其余境外站点直连可能超时，境内站点（如 bing.com）通常可达。"
        "某站点连续不可达时请换可达源或尽快回禀，不要反复撞同一批境外域名。"
    )


def _salvage_clues(messages: list, limit: int = 3, width: int = 150) -> list[str]:
    """阶段十五 15.3 收兵打捞：从历史里捞最近 N 条非失败的工具结果当线索。

    同日事故的另一面：东厂探事第 5 轮就读到了答案（本地文书里的仓库网址），
    却因超轮收兵没能带回，总管两手空空只能自己重查一遍。失败结果不计入线索
    （失败已有统计与原因覆盖），线索随收兵文案一并回禀。
    """
    clues: list[str] = []
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "").strip()
        if not content or _is_tool_failure(content):
            continue
        clues.append(" ".join(content.split())[:width])  # 压平空白再截，回禀不吞版面
    return clues[-limit:]


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


class _RunLogger:
    """子代理执行日志（任务 5.2）：一次派遣一个 jsonl，记 start/tool/end 三类事件。

    oxalpha 事件里子代理内部完全不可观测——失败只能靠主对话记录反推。
    事件字段：ts / event /（start: agent_type, task, purpose, env_note 前 300 字——
    阶段十五 15.2 起，task 恒为原始差事原文、路况说明独立成字段，不挤占截断口径）
    （tool: turn, tool, ok, result 前 200 字）（end: outcome=done|circuit_breaker|
    max_turns|llm_error, turns_used, ok, fail, summary 前 200 字）。
    目录 memory/subagent_logs/（已被 .gitignore 的 memory/ 覆盖）。
    """

    def __init__(self, agent_type: str, task: str, purpose: str, env_note: str = ""):
        SUBAGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.path = SUBAGENT_LOG_DIR / (
            f"{datetime.now():%Y%m%d-%H%M%S}-{agent_type}-{uuid.uuid4().hex[:6]}.jsonl"
        )
        self.log(event="start", agent_type=agent_type, task=task[:500], purpose=purpose,
                 env_note=env_note[:300])

    def log(self, **kw) -> None:
        kw["ts"] = datetime.now().isoformat(timespec="seconds")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")

    def tool(self, turn: int, name: str, ok: bool, result: str) -> None:
        self.log(event="tool", turn=turn, tool=name, ok=ok, result=str(result)[:200])

    def end(self, outcome: str, turns_used: int, ok: int, fail: int, summary: str) -> None:
        self.log(event="end", outcome=outcome, turns_used=turns_used,
                 ok=ok, fail=fail, summary=str(summary)[:200])


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

    # 阶段十五 15.2：路况说明先于日志生成——start 事件的 task 保持差事原文，
    # 说明另记 env_note 字段；随后才拼进子代理实际收到的差事里。
    env_note = _network_env_note(spec["tools"])
    logger = _RunLogger(agent_type, task, purpose, env_note=env_note)
    if env_note:
        task = f"{env_note}\n\n{task}"

    # 阶段十：工具执行走统一守卫入口（Hook 链全端生效，confirmer=None → ask 自动拒绝）。
    # 函数内导入：registry 顶层 import 本模块（派遣选项），模块级互相导入会成环（team.py 先例）。
    from .registry import execute_guarded

    messages = [{"role": "user", "content": task}]
    consecutive_failures = 0
    ok_count = 0
    fail_count = 0

    for turn in range(turns):
        msg, llm_err = _call_llm_with_retry(spec["system_prompt"], messages, tools)
        if msg is None:
            # 阶段十四（债⑤）：模型调用失败降级为文字回禀，不抛异常击穿主循环
            text = _llm_failure_message(llm_err, _salvage_clues(messages))
            print(f"  └── 模型调用失败，提前收兵（第 {turn + 1} 轮）：{llm_err} ──\n")
            print(f"[小太监回禀]: {text}\n")
            logger.end(outcome="llm_error", turns_used=turn + 1,
                       ok=ok_count, fail=fail_count, summary=text)
            return text
        messages.append(assistant_to_dict(msg))

        if not msg.tool_calls:
            final = msg.content or ""
            print(f"  └── subagent context end (内部 {turn + 1} 轮，回传 {len(final)} 字) ──")
            print(f"[小太监回禀]: {final}\n")
            logger.end(outcome="done", turns_used=turn + 1, ok=ok_count, fail=fail_count, summary=final)
            return final

        for tc in msg.tool_calls:
            block = to_tool_call(tc)
            content = execute_guarded(
                block.name, block.input,
                sender=f"subagent:{agent_type}", prefix=f"子({spec['title']})·",
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": content,
            })
            failed = _is_tool_failure(content)
            if failed:
                consecutive_failures += 1
                fail_count += 1
            else:
                consecutive_failures = 0
                ok_count += 1
            logger.tool(turn=turn + 1, name=block.name, ok=not failed, result=content)

        # 熔断检查放在整批工具执行完之后：协议要求每个 tool_call 都要有配对结果
        if consecutive_failures >= _fail_budget():
            text = _circuit_breaker_message(consecutive_failures, turn + 1,
                                            _salvage_clues(messages))
            print(f"  └── 连续 {consecutive_failures} 次工具失败，触发熔断提前收兵（第 {turn + 1} 轮）──\n")
            print(f"[小太监回禀]: {text}\n")
            logger.end(outcome="circuit_breaker", turns_used=turn + 1,
                       ok=ok_count, fail=fail_count, summary=text)
            return text

    text = _max_turns_message(turns, ok_count, fail_count, _salvage_clues(messages))
    print(f"  └── subagent context end (达到 {turns} 轮上限，成功 {ok_count} / 失败 {fail_count}) ──\n")
    print(f"[小太监回禀]: {text}\n")
    logger.end(outcome="max_turns", turns_used=turns, ok=ok_count, fail=fail_count, summary=text)
    return text
