"""config."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

API_KEY = os.getenv("API_KEY", "")

LIGHT_DREAM_API_KEY = (
    os.getenv("LIGHT_DREAM_API_KEY", "").strip() or API_KEY
)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

MAIN_MODEL = os.getenv("MAIN_MODEL", "deepseek/deepseek-v4-flash")

LIGHT_DREAM_MODEL = os.getenv("LIGHT_DREAM_MODEL", MAIN_MODEL)

MODEL_CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_WINDOW", "1000000"))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

TOOL_CACHE_DEFAULT_TTL_SECONDS = int(os.getenv("TOOL_CACHE_DEFAULT_TTL_SECONDS", "3600"))

ENABLE_LLM_STATS = os.getenv("ENABLE_LLM_STATS", "false").lower() in ("1", "true", "yes")
API_BASE = os.getenv("API_BASE", "").strip()
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "").strip()
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-litellm-local")

DATA_DIR = BACKEND_DIR / "data"
USERS_DIR = BACKEND_DIR / "users"
SKILLS_DIR = BACKEND_DIR / "skills"
SAFETY_LOG_PATH = DATA_DIR / "safety_log.jsonl"

def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")

APPROVAL_TIMEOUT_SECONDS = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "10"))
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "5"))
TASK_RESULT_TTL_SECONDS = int(os.getenv("TASK_RESULT_TTL_SECONDS", "3600"))
TASK_CLAIM_IDLE_MS = int(os.getenv("TASK_CLAIM_IDLE_MS", "60000"))

SEARCH_SAFE_MODE = _env_bool("SEARCH_SAFE_MODE", "false")
SEARCH_WHITELIST_PATH = DATA_DIR / "search_whitelist.json"

DOCS_AGENT_MODEL = os.getenv("DOCS_AGENT_MODEL", MAIN_MODEL)
DOCS_AGENT_API_KEY = os.getenv("DOCS_AGENT_API_KEY", "").strip() or API_KEY
DOCS_AGENT_API_BASE = os.getenv("DOCS_AGENT_API_BASE", "").strip() or API_BASE

DRUG_CLASSI_DB_PATH = DATA_DIR / "drug_classi_db" / "drug_classi.db"
MEDICAL_DOCS_DIR = DATA_DIR / "medical_docs"
DOCS_INDEX_DB_PATH = DATA_DIR / "docs_index.db"

PROMPT_GUARD_BLOCK_THRESHOLD = float(os.getenv("PROMPT_GUARD_BLOCK_THRESHOLD", "0.8"))
PROMPT_GUARD_WARN_THRESHOLD = float(os.getenv("PROMPT_GUARD_WARN_THRESHOLD", "0.3"))

SECURITY_CONFIG = {
    "query": {
        "enabled": _env_bool("SECURITY_QUERY_ENABLED"),
        "keyword": _env_bool("SECURITY_QUERY_KEYWORD"),
        "semantic": _env_bool("SECURITY_QUERY_SEMANTIC", "false"),
    },
    "reply_stream": {
        "enabled": _env_bool("SECURITY_REPLY_STREAM_ENABLED"),
        "keyword": _env_bool("SECURITY_REPLY_STREAM_KEYWORD"),
        "semantic": _env_bool("SECURITY_REPLY_STREAM_SEMANTIC", "false"),
    },
    "reply": {
        "enabled": _env_bool("SECURITY_REPLY_ENABLED"),
        "keyword": _env_bool("SECURITY_REPLY_KEYWORD"),
        "semantic": _env_bool("SECURITY_REPLY_SEMANTIC", "false"),
    },
}

EVAL_MODE = _env_bool("EVAL_MODE", "false")

if EVAL_MODE:
    for _scene_cfg in SECURITY_CONFIG.values():
        _scene_cfg["enabled"] = False
SECURITY_STREAM_WINDOW = int(os.getenv("SECURITY_STREAM_WINDOW", "64"))
SECURITY_STREAM_OVERLAP = int(os.getenv("SECURITY_STREAM_OVERLAP", "16"))

def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    MEDICAL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
