"""记录模型调用的 token 用量和缓存命中情况。"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, asdict
from typing import Optional

from backend.config import ENABLE_LLM_STATS, USERS_DIR


@dataclass
class LLMStats:
    stage: str = ""
    chat_id: str = ""
    username: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    cache_hit_rate: float = 0.0
    ttft_ms: float = 0.0
    e2e_latency_ms: float = 0.0
    tool_call_count: int = 0
    timestamp: float = 0.0


def report(stats: LLMStats) -> None:
    stats.timestamp = time.time()
    _print_stats(stats)
    if ENABLE_LLM_STATS and stats.username:
        _store_stats(stats)


def _print_stats(s: LLMStats) -> None:
    cache_part = f"cache={s.cache_hit_rate:.0%} " if s.input_tokens > 0 else ""
    ttft_part = f"ttft={s.ttft_ms:.0f}ms " if s.ttft_ms > 0 else ""
    print(
        f"[LLM统计] {s.stage or '(unknown)'} | "
        f"in={s.input_tokens} out={s.output_tokens} {cache_part}| "
        f"{ttft_part}e2e={s.e2e_latency_ms:.0f}ms | "
        f"tools={s.tool_call_count}"
    )


def _get_db_path(username: str):
    return USERS_DIR / username / "messages.db"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     TEXT,
            stage       TEXT,
            model       TEXT,
            input_tokens    INTEGER,
            output_tokens   INTEGER,
            cache_hit_tokens  INTEGER,
            cache_miss_tokens INTEGER,
            cache_hit_rate  REAL,
            ttft_ms     REAL,
            e2e_latency_ms REAL,
            tool_call_count INTEGER,
            created_at  REAL
        )
    """)


def _store_stats(s: LLMStats) -> None:
    try:
        db_path = _get_db_path(s.username)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        _ensure_table(conn)
        conn.execute(
            """INSERT INTO llm_stats
               (chat_id, stage, model, input_tokens, output_tokens,
                cache_hit_tokens, cache_miss_tokens, cache_hit_rate,
                ttft_ms, e2e_latency_ms, tool_call_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s.chat_id, s.stage, s.model,
                s.input_tokens, s.output_tokens,
                s.cache_hit_tokens, s.cache_miss_tokens, s.cache_hit_rate,
                s.ttft_ms, s.e2e_latency_ms,
                s.tool_call_count, s.timestamp,
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LLM统计] 写入数据库失败（已忽略）：{e}")


def extract_cache_info(usage) -> tuple[int, int]:
    if not usage:
        return 0, 0

    hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
    miss = getattr(usage, "prompt_cache_miss_tokens", 0) or 0
    if hit or miss:
        return hit, miss

    details = getattr(usage, "prompt_tokens_details", None)
    if details:
        cached = getattr(details, "cached_tokens", 0) or 0
        if cached:
            total_prompt = getattr(usage, "prompt_tokens", 0) or 0
            return cached, max(0, total_prompt - cached)

    return 0, 0
