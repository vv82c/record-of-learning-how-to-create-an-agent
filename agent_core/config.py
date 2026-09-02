"""集中管理项目路径常量，避免各模块各自拼路径。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
MEMORY_DIR = PROJECT_ROOT / "memory"
SESSIONS_DIR = MEMORY_DIR / "sessions"
SUBAGENT_LOG_DIR = MEMORY_DIR / "subagent_logs"
AUDIT_MAX_BYTES = int(__import__("os").environ.get("EMPEROR_AUDIT_MAX_BYTES", str(5 * 1024 * 1024)))
AUDIT_MAX_BACKUPS = int(__import__("os").environ.get("EMPEROR_AUDIT_MAX_BACKUPS", "3"))
# 模型上下文窗口（E5 内库账房算占用率用）：换模型时在 .env 配 LLM_CONTEXT_WINDOW 覆盖
CONTEXT_WINDOW = int(__import__("os").environ.get("LLM_CONTEXT_WINDOW", "131072"))
TEMPLATES_DIR = PROJECT_ROOT / "templates"
MCP_CONFIG_PATH = PROJECT_ROOT / "mcp_servers.json"
AUDIT_FILE = PROJECT_ROOT / ".hooks_audit.jsonl"
TEAM_DIR = PROJECT_ROOT / ".team"
INBOX_DIR = TEAM_DIR / "inbox"
COMPACT_PROMPT_PATH = TEMPLATES_DIR / "agent" / "compact_prompt.md"
PERSONA_DIR = TEMPLATES_DIR / "persona"
