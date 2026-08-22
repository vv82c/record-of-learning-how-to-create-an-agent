"""内置工具：schema 定义与执行（run_command / web_fetch / read_file / write_file / glob / grep / load_skill）。"""
from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

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


def web_fetch(url: str, extract_mode: str = "text", max_chars: int = 8000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Error fetching {url}: {e}"

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
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        output = result.stdout or result.stderr
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
