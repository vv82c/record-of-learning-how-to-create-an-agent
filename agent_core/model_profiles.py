"""模型配置中心（F1）：多模型档案 + 活跃配置，存 model_profiles.json。

- 文件在 PROJECT_ROOT（已 gitignore——含 API Key，与 .env 同级敏感）
- 首次加载若文件缺失且 .env 齐备，自动把 .env 种子为第一个档案（无缝迁移）；
  此后 .env 退化为兜底：删掉配置文件也能照常启动
- upsert 时同名档案传入空 api_key 视为"沿用原 key"（前端回传的是打码表单，
  用户没填新 key 就不能覆盖旧值）
"""
from __future__ import annotations

import json
import os

from .config import PROJECT_ROOT

PROFILES_FILE = PROJECT_ROOT / "model_profiles.json"


def _from_env() -> dict | None:
    """.env 齐备时构造一个种子档案（迁移与兜底的共同来源）。"""
    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not base_url or not model:
        return None
    return {"name": model, "base_url": base_url, "api_key": api_key,
            "model": model, "context_window": None}


def load() -> dict:
    """读配置；文件缺失/损坏时用 .env 种子并落盘。返回 {"active": str|None, "profiles": [...]}。"""
    data = None
    if PROFILES_FILE.exists():
        try:
            data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        seeded = _from_env()
        data = {"active": seeded["name"] if seeded else None,
                "profiles": [seeded] if seeded else []}
        if seeded:
            save(data["profiles"], data["active"])
    # 清洗：保留 base_url/model 齐全的档案
    profiles = [p for p in data["profiles"]
                if isinstance(p, dict) and p.get("base_url") and p.get("model")]
    active = data.get("active")
    if active not in [p["name"] for p in profiles]:
        active = profiles[0]["name"] if profiles else None
    return {"active": active, "profiles": profiles}


def save(profiles: list[dict], active: str | None) -> None:
    PROFILES_FILE.write_text(
        json.dumps({"active": active, "profiles": profiles}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def upsert(profile: dict) -> dict:
    """新增或更新一条档案并落盘，返回最新配置。空 key 沿用旧值。"""
    data = load()
    for i, p in enumerate(data["profiles"]):
        if p["name"] == profile["name"]:
            if not profile.get("api_key") and p.get("api_key"):
                profile["api_key"] = p["api_key"]
            data["profiles"][i] = profile
            break
    else:
        data["profiles"].append(profile)
    if not data.get("active"):
        data["active"] = profile["name"]
    save(data["profiles"], data["active"])
    return data


def activate(name: str) -> dict | None:
    """切换活跃档案，返回该档案（未知名字返回 None）。"""
    data = load()
    for p in data["profiles"]:
        if p["name"] == name:
            data["active"] = name
            save(data["profiles"], name)
            return p
    return None


def delete(name: str) -> dict:
    """删除档案；删到活跃档案则自动切给第一个剩余的（没有则 active=None）。"""
    data = load()
    data["profiles"] = [p for p in data["profiles"] if p["name"] != name]
    if data["active"] == name:
        data["active"] = data["profiles"][0]["name"] if data["profiles"] else None
    save(data["profiles"], data["active"])
    return data


def get_active() -> dict | None:
    """当前活跃档案；未配置返回 None（call_llm 会走引导文案）。"""
    data = load()
    for p in data["profiles"]:
        if p["name"] == data["active"]:
            return p
    return None
