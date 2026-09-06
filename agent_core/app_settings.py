"""统一设置中心（阶段九 / UIPLAN 阶段 I）：行为旋钮的单一数据源。

与 model_profiles 的分工：模型阁管"接哪个模型"（连接档案），本模块管"软件怎么行事"
（批阅时限 / 默认人格 / 熔断预算）。与 .env 的关系：.env 是首次启动的种子值，
settings.json 是用户在界面上改出来的当前值——文件不存在/损坏时静默回落种子，永不崩。

运行时生效的关键：**消费点每次使用时都调 load() 读现值**，而不是模块加载时读一次——
这与 llm.apply_profile 的"属性引用"是同一个教训的两处应用。
上下文窗口不在此管：它是模型档案的属性（模型阁表单），随档案切换，全局设只会打架。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import PERSONA_DIR

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.json"

# 合法区间：界面表单与服务端共用这一份语义（服务端 save 时强校验）
ASK_TIMEOUT_RANGE = (5.0, 600.0)
FAIL_BUDGET_RANGE = (1, 10)


def _env_seed() -> dict:
    """.env / 缺省值构成种子层：只在 settings.json 缺失或损坏时整体可见。"""
    return {
        "ask_timeout": float(os.environ.get("EMPEROR_ASK_TIMEOUT", "120")),
        "default_persona": os.environ.get("AGENT_PERSONA", ""),
        "subagent_fail_budget": int(os.environ.get("AGENT_SUBAGENT_FAIL_BUDGET", "3")),
    }


def _validate(patch: dict) -> dict:
    """类型收敛 + 区间校验。非法值抛 ValueError（REST 层转 400），不静默吞。"""
    out = {}
    if "ask_timeout" in patch:
        try:
            v = float(patch["ask_timeout"])
        except (TypeError, ValueError):
            raise ValueError("批阅时限必须是数字（秒）")
        if not (ASK_TIMEOUT_RANGE[0] <= v <= ASK_TIMEOUT_RANGE[1]):
            raise ValueError(f"批阅时限须在 {ASK_TIMEOUT_RANGE[0]:.0f}~{ASK_TIMEOUT_RANGE[1]:.0f} 秒之间")
        out["ask_timeout"] = v
    if "subagent_fail_budget" in patch:
        try:
            v = int(patch["subagent_fail_budget"])
        except (TypeError, ValueError):
            raise ValueError("熔断预算必须是整数（次）")
        if not (FAIL_BUDGET_RANGE[0] <= v <= FAIL_BUDGET_RANGE[1]):
            raise ValueError(f"熔断预算须在 {FAIL_BUDGET_RANGE[0]}~{FAIL_BUDGET_RANGE[1]} 次之间")
        out["subagent_fail_budget"] = v
    if "default_persona" in patch:
        name = str(patch["default_persona"] or "").strip()
        if name and not (PERSONA_DIR / f"{name}.md").exists():
            raise ValueError(f"未知人格：{name}")
        out["default_persona"] = name
    unknown = set(patch) - {"ask_timeout", "default_persona", "subagent_fail_budget"}
    if unknown:
        raise ValueError(f"未知设置项：{', '.join(sorted(unknown))}")
    return out


def load() -> dict:
    """种子 ← 文件 逐层覆盖后的当前值。文件缺失/损坏静默回落（settings.json 是用户手改的，坏了别炸内核）。"""
    merged = _env_seed()
    if SETTINGS_PATH.exists():
        try:
            file_vals = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(file_vals, dict):
                merged.update({k: v for k, v in file_vals.items() if k in merged})
        except (OSError, json.JSONDecodeError):
            pass
    return merged


def save(patch: dict) -> dict:
    """校验 → 合并落盘 → 返回合并后的当前值。只收合法键，一次只改用户提交的项。"""
    clean = _validate(patch or {})
    merged = load()
    merged.update(clean)
    SETTINGS_PATH.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
