"""控制台 UTF-8 保障（发布后修复：GBK 内核异常）。

Windows 中文环境默认控制台编码是 GBK（cp936）。模型回复里的 emoji
（如天气 🌤）经任何 print() 写入 GBK 控制台都会抛 UnicodeEncodeError，
直接炸掉内核线程（用户表现为"[内核异常] gbk codec can't encode ..."）。

修复策略：入口启动时把 stdout/stderr reconfigure 成 UTF-8，且
errors="replace"——即使再遇到奇异字符也只会显示替代符，绝不抛异常。
"""
from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """把标准输出/错误流切换为 UTF-8（errors=replace）。幂等，无流时安全跳过。

    三个入口都要调用：run_app.py（exe）、web/server.py（服务/开发）、main.py（终端）。
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:  # exe 无控制台模式下 stdout 可能为 None
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            # 任何原因（如流已关闭）都不值得为打印编码打断启动
            pass
