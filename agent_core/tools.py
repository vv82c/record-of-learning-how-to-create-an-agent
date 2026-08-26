"""内置工具：schema 定义与执行（run_command / web_fetch / read_file / write_file / glob / grep / load_skill）。"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from .skills import SKILL_LOADER


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self):
        return re.sub(r"\n{3,}", "\n\n", "".join(self._parts)).strip()


# ============== SSRF 防护（任务 2.3） ==============
# web_fetch 能替 Agent 访问任意 URL。若不设限，一段提示注入就能指挥它去摸
# 本机服务、路由器管理页或云元数据接口（169.254.169.254）。
# 防护做在工具函数内部，主 Agent、子代理、队友的调用都自动生效。
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),     # IPv4 回环：整个 127 段都指本机
    ipaddress.ip_network("0.0.0.0/8"),       # "未知地址"，部分系统按本机处理
    ipaddress.ip_network("10.0.0.0/8"),      # 私有网段（A 类）
    ipaddress.ip_network("172.16.0.0/12"),   # 私有网段（B 类，172.16 ~ 172.31）
    ipaddress.ip_network("192.168.0.0/16"),  # 私有网段（C 类）
    ipaddress.ip_network("169.254.0.0/16"),  # 链路本地：云厂商元数据服务所在段
    ipaddress.ip_network("::1/128"),         # IPv6 回环
    ipaddress.ip_network("fe80::/10"),       # IPv6 链路本地
]
BLOCKED_HOSTNAMES = {"localhost"}


class BlockedAddressError(Exception):
    """SSRF 防护：目标解析到本机/内网/保留地址。"""


class DNSResolveError(BlockedAddressError):
    """域名解析失败：域名不存在、DNS 受限或未联网。

    继承 BlockedAddressError 是为了让既有的 except 捕获点继续工作，
    但语义上它不是"拦截"——web_fetch 会用独立文案区分（任务 5.3）。
    """


def _is_blocked_address(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in BLOCKED_NETWORKS)


def assert_url_allowed(url: str) -> None:
    """SSRF 检查，不通过则抛 BlockedAddressError。

    1) 主机名是 localhost 或 IP 字面量 → 直接判断；
    2) 域名 → getaddrinfo 解析出全部 IP 逐一判断，堵住"域名解析到内网"的绕过。
    局限：检查与实际连接各自解析一次 DNS，理论上存在 TOCTOU 竞态（DNS rebinding），
    教学版不做到"锁定已解析 IP 直连"的程度。
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise BlockedAddressError(f"URL 中解析不出主机名（非 http(s) 地址？）：{url}")
    if host in BLOCKED_HOSTNAMES:
        raise BlockedAddressError(f"目标主机名为 localhost，已拦截：{url}")
    if _is_blocked_address(host):
        raise BlockedAddressError(f"目标 {host} 属于内网/保留地址段，已拦截：{url}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise DNSResolveError(f"主机名解析失败：{host}（{exc}）")
    for info in infos:
        ip = info[4][0]
        if _is_blocked_address(ip):
            raise BlockedAddressError(f"{host} 解析到内网/保留地址 {ip}，已拦截：{url}")


class _SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
    """30x 重定向的目标同样要过 SSRF 检查，否则"外网 URL 跳内网"就能绕过防护。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_url_allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def web_fetch(url: str, extract_mode: str = "text", max_chars: int = 8000) -> str:
    try:
        assert_url_allowed(url)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        opener = urllib.request.build_opener(_SSRFRedirectHandler)
        with opener.open(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except DNSResolveError as e:
        # 解析失败 ≠ 被拦截（任务 5.3）：域名可能不存在，也可能 DNS 受限/未联网。
        # 错误信息附带提示，引导模型换源而不是反复撞同一个域名。
        return (
            f"Error: {e}\n"
            "[提示] 域名解析失败：可能域名不存在、DNS 受限或未联网；建议改用其他可达域名再试。"
        )
    except BlockedAddressError as e:
        return f"Error: SSRF 防护已拦截：{e}"
    except Exception as e:
        text = f"Error fetching {url}: {e}"
        if "timed out" in str(e).lower():
            # oxalpha 事件复盘：直连境外站大量超时时，模型只会瞎换 URL。
            # 给出明确提示，引导它切换到当前网络可达的源。
            text += (
                "\n[提示] 连接超时：目标站点在当前网络不可达（境外站点未挂代理时常见），"
                "建议换可达源（如 bing.com 搜索或国内站点）再试，不要反复撞同一批境外域名。"
            )
        return text

    if extract_mode == "text":
        parser = _TextExtractor()
        parser.feed(raw)
        text = parser.get_text()
    else:
        text = raw

    return text[:max_chars]


def grep_search(pattern: str, path: str = ".", max_results: int = 200) -> str:
    """纯 Python 实现的递归 grep，跨平台（Windows 上没有系统 grep 命令）。

    行为对齐 grep -rn --include=*.py --include=*.md：输出格式为 路径:行号:内容。
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: 无效的正则表达式 '{pattern}': {e}"

    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    include_suffixes = {".py", ".md"}
    root = Path(path)

    if root.is_file():
        files = [root]
    elif root.is_dir():
        files = [
            f for f in sorted(root.rglob("*"))
            if f.is_file() and f.suffix in include_suffixes
            and not any(part in skip_dirs for part in f.relative_to(root).parts[:-1])
        ]
    else:
        return f"Error: 路径不存在 '{path}'"

    matches = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{f}:{line_no}:{line.strip()}")
                if len(matches) >= max_results:
                    matches.append(f"...(匹配结果过多，已截断至 {max_results} 条)")
                    return "\n".join(matches)

    return "\n".join(matches) if matches else "(无匹配)"


# ============== 工具 schema 定义 ==============
TOOL_SCHEMAS: dict[str, dict] = {
    "run_command": {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在终端执行一条命令并返回输出。创建或覆盖文件必须调用 write_file。",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "要执行的 shell 命令"}},
                "required": ["command"]
            }
        }
    },
    "web_fetch": {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "获取指定 URL 的网页内容，支持文本提取模式",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":          {"type": "string",  "description": "要访问的完整 URL"},
                    "extract_mode": {"type": "string",  "description": "提取模式：text（纯文本，默认）或 raw（原始 HTML）"},
                    "max_chars":    {"type": "integer", "description": "最大返回字符数，默认 8000"}
                },
                "required": ["url"]
            }
        }
    },
    "load_skill": {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "加载指定技能的详细知识内容，在回答相关问题前调用",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "技能名称，必须是系统提示中列出的可用技能之一"}
                },
                "required": ["skill_name"]
            }
        }
    },
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地文件内容",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"]
            }
        }
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件内容（覆盖）。创建或覆盖文件必须调用这个工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    "glob": {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "按 glob 模式搜索工作区文件",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"]
            }
        }
    },
    "grep": {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在工作区文件中搜索文本内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path":    {"type": "string"}
                },
                "required": ["pattern"]
            }
        }
    },
}


COMMAND_TIMEOUT_SECONDS = 120  # run_command 默认超时（任务 2.2）：防止卡死的命令挂起整个会话


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """超时时杀掉整个进程树。

    subprocess 自带的 kill() 只杀直接子进程（shell）。Windows 上孙进程会残留，
    还继承着输出管道的写端——这是 subprocess.run(timeout=...) 在 shell=True 下
    收尾无限阻塞的根源，所以必须整树击杀。
    """
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def _decode_child_output(data: bytes) -> str:
    """子进程输出解码（发布后修复④）：UTF-8 → Windows 原生编码（cp936/mbcs）→ replace 兜底。

    背景：中文 Windows 上 cmd/PowerShell/系统命令的输出是 GBK/cp936 字节，
    直接按 UTF-8 读会成片 U+FFFD（工具卡里的菱形问号）；而 python 子进程
    自己打印的又常是 UTF-8。无法预知，按序探测。

    不用 locale.getpreferredencoding()——它在 Git Bash/IDE 等环境会被 LANG/LC_*
    污染返回 "UTF-8"，与 Windows 控制台真实代码页不符。sys.stdout.encoding 才是
    Python 启动时锁定的真实控制台编码。
    """
    candidates = ["utf-8"]
    win_default = sys.stdout.encoding if sys.stdout else None
    if win_default and win_default.lower().replace("-", "") not in ("utf8", "utf", "utf16"):
        candidates.append(win_default)
    for fallback in ("cp936", "mbcs", "gbk"):
        if fallback not in candidates:
            candidates.append(fallback)
    for enc in candidates:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_shell_command(command: str, timeout: int = COMMAND_TIMEOUT_SECONDS) -> str:
    """执行 shell 命令并返回输出文本；超时则杀掉进程树并返回错误说明。

    输出经临时文件中转而不是管道：管道的写端会被孙进程继承，超时杀掉 shell 后
    仍等不到 EOF，整个会话会被卡到孙进程自己退出为止。
    临时文件用二进制模式写：子进程输出编码（GBK/UTF-8）未知，读回时探测解码。
    """
    with tempfile.TemporaryFile("w+b") as out_f, \
         tempfile.TemporaryFile("w+b") as err_f:
        popen_kwargs = {"stdout": out_f, "stderr": err_f, "shell": True}
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True  # 独立进程组，便于 killpg 整树击杀
        proc = subprocess.Popen(command, **popen_kwargs)
        try:
            proc.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            proc.communicate()  # 回收退出状态；文件方案下不会再阻塞
            timed_out = True
        out_f.seek(0)
        err_f.seek(0)
        stdout = _decode_child_output(out_f.read())
        stderr = _decode_child_output(err_f.read())

    if timed_out:
        text = f"Error: 命令超过 {timeout} 秒未完成，进程树已被强制终止（TimeoutExpired）。"
        if (stdout or stderr).strip():
            text += f"\n超时前已捕获的部分输出：\n{stdout or stderr}"
        return text
    return stdout or stderr


def execute_basic_tool(block: SimpleNamespace, prefix: str = "") -> str:
    """处理基础工具，返回字符串内容。
    prefix 用于在终端打印时区分主/子上下文（例如 prefix='子·'）。"""
    if block.name == "web_fetch":
        url = block.input["url"]
        mode = block.input.get("extract_mode", "text")
        max_chars = block.input.get("max_chars", 8000)
        print(f"  [{prefix}网页获取]: {url}")
        return web_fetch(url, mode, max_chars)

    if block.name == "run_command":
        command = block.input["command"]
        print(f"  [{prefix}执行命令]: {command}")
        output = run_shell_command(command, COMMAND_TIMEOUT_SECONDS)
        print(f"  [{prefix}命令输出]: {output.strip()[:200]}")
        return output

    if block.name == "load_skill":
        skill_name = block.input["skill_name"]
        print(f"  [{prefix}加载技能]: {skill_name}")
        return SKILL_LOADER.get_content(skill_name)

    if block.name == "read_file":
        path = block.input["path"]
        print(f"  [{prefix}读取文件]: {path}")
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {path}: {e}"

    if block.name == "write_file":
        path = block.input["path"]
        content = block.input["content"]
        print(f"  [{prefix}写入文件]: {path}")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"写入成功: {path}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    if block.name == "glob":
        pattern = block.input["pattern"]
        print(f"  [{prefix}文件搜索]: {pattern}")
        matches = sorted(str(p) for p in Path(".").glob(pattern))
        return "\n".join(matches) if matches else "(无匹配)"

    if block.name == "grep":
        pattern = block.input["pattern"]
        path = block.input.get("path", ".")
        print(f"  [{prefix}内容搜索]: {pattern} in {path}")
        return grep_search(pattern, path)

    return f"Error: Unknown tool '{block.name}'"
