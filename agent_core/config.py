"""集中管理项目路径常量，避免各模块各自拼路径。"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
MEMORY_DIR = PROJECT_ROOT / "memory"
SESSIONS_DIR = MEMORY_DIR / "sessions"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
MCP_CONFIG_PATH = PROJECT_ROOT / "mcp_servers.json"
AUDIT_FILE = PROJECT_ROOT / ".hooks_audit.jsonl"
TEAM_DIR = PROJECT_ROOT / ".team"
INBOX_DIR = TEAM_DIR / "inbox"
COMPACT_PROMPT_PATH = TEMPLATES_DIR / "agent" / "compact_prompt.md"
PERSONA_DIR = TEMPLATES_DIR / "persona"
