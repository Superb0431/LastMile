"""缓存心跳：在厂商 KVCache 过期前发轻量请求续命。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime

from backend.agent import llm
from backend.agent.context_builder import build_context
from backend.config import (
    DATA_DIR,
    HEARTBEAT_ENABLED,
    HEARTBEAT_MAX_PINGS,
    MAIN_MODEL,
)
from backend.prompts.main_agent import CACHE_HEARTBEAT_SENTINEL
from backend.tools import registry


PROVIDER_CACHE_TTL_SECONDS: dict[str, int] = {
    "openai": 24 * 3600,
    "anthropic": 1 * 3600,
    "deepseek": 24 * 3600,
    "kimi": 1 * 3600,
    "moonshot": 1 * 3600,
    "gemini": 1 * 3600,
}

_BACKOFF_SECONDS = [5, 20, 60]
_CONCURRENCY_LIMIT = asyncio.Semaphore(5)

HEARTBEAT_LOG_PATH = DATA_DIR / "heartbeat_log.jsonl"


@dataclass
class _Lease:
    username: str
    chat_id: str
    last_real_activity_at: float
    last_heartbeat_at: float | None = None
    ping_count: int = 0


_leases: dict[tuple[str, str], _Lease] = {}
_busy: set[tuple[str, str]] = set()


def _session_key(username: str, chat_id: str) -> tuple[str, str]:
    return (username, chat_id)


def get_cache_ttl_seconds(model: str) -> int:
    provider = model.split("/")[0].lower() if model else ""
    return PROVIDER_CACHE_TTL_SECONDS.get(provider, 3600)


def touch(username: str, chat_id: str) -> None:
    key = _session_key(username, chat_id)
    _leases[key] = _Lease(
        username=username,
        chat_id=chat_id,
        last_real_activity_at=time.time(),
    )


def mark_busy(username: str, chat_id: str) -> None:
    _busy.add(_session_key(username, chat_id))


def mark_idle(username: str, chat_id: str) -> None:
    _busy.discard(_session_key(username, chat_id))


def _scan_interval_seconds() -> int:
    ttl = get_cache_ttl_seconds(MAIN_MODEL)
    return max(30, min(5 * 60, ttl // 2 or 30))


def _interval_label(ttl_seconds: int) -> str:
    if ttl_seconds >= 3600 and ttl_seconds % 3600 == 0:
        return f"{ttl_seconds // 3600}h"
    if ttl_seconds >= 60 and ttl_seconds % 60 == 0:
        return f"{ttl_seconds // 60}min"
    return f"{ttl_seconds}s"


def _append_log(record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HEARTBEAT_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _log_result(
    username: str,
    chat_id: str,
    *,
    success: bool,
    reply: str = "",
    error: str | None = None,
    input_tokens: int = 0,
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
    hit_rate: float = 0.0,
) -> None:
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "username": username,
        "chat_id": chat_id,
        "success": success,
        "reply": reply,
        "error": error,
        "input_tokens": input_tokens,
        "cache_hit_tokens": cache_hit_tokens,
        "cache_miss_tokens": cache_miss_tokens,
        "hit_rate": round(hit_rate, 4),
    }
    _append_log(record)
    hit_note = ""
    if success:
        hit_note = (
            f" in={input_tokens} 命中={cache_hit_tokens} "
            f"未命中={cache_miss_tokens} ({hit_rate:.0%})"
        )
    print(
        f"[心跳] {record['time']} {username}/{chat_id} "
        f"success={success}{hit_note} reply={reply!r}"
        + (f" error={error}" if error else "")
    )


async def _send_heartbeat(username: str, chat_id: str) -> bool:
    last_error: Exception | None = None

    for attempt, wait in enumerate(_BACKOFF_SECONDS, start=1):
        try:
            async with _CONCURRENCY_LIMIT:
                messages = build_context(chat_id, username)
                messages.append(
                    {"role": "user", "content": CACHE_HEARTBEAT_SENTINEL}
                )
                text, stats = await llm.complete(
                    messages,
                    tools=registry.get_initial_tools(),
                    max_tokens=1,
                    return_stats=True,
                    stage="heartbeat",
                    chat_id=chat_id,
                    username=username,
                )
            _log_result(
                username,
                chat_id,
                success=True,
                reply=text,
                input_tokens=stats.input_tokens,
                cache_hit_tokens=stats.cache_hit_tokens,
                cache_miss_tokens=stats.cache_miss_tokens,
                hit_rate=stats.cache_hit_rate,
            )
            return True
        except Exception as error:
            last_error = error
            print(
                f"[心跳] {username}/{chat_id} 第{attempt}次失败：{error}，"
                f"{wait} 秒后重试"
            )
            await asyncio.sleep(wait)

    _log_result(
        username,
        chat_id,
        success=False,
        error=str(last_error) if last_error else "unknown",
    )
    return False


async def _ping_lease(lease: _Lease) -> None:
    key = _session_key(lease.username, lease.chat_id)
    activity_at = lease.last_real_activity_at

    ok = await _send_heartbeat(lease.username, lease.chat_id)

    current = _leases.get(key)
    if current is None or current.last_real_activity_at != activity_at:
        return
    if key in _busy:
        return
    if not ok:
        return

    current.ping_count += 1
    current.last_heartbeat_at = time.time()
    if current.ping_count >= HEARTBEAT_MAX_PINGS:
        _leases.pop(key, None)


def _due_leases(now: float, ttl: int) -> list[_Lease]:
    due: list[_Lease] = []
    for key, lease in list(_leases.items()):
        if key in _busy:
            continue
        if HEARTBEAT_MAX_PINGS <= 0 or lease.ping_count >= HEARTBEAT_MAX_PINGS:
            _leases.pop(key, None)
            continue
        if now - lease.last_real_activity_at < ttl:
            continue
        if lease.last_heartbeat_at is not None and now - lease.last_heartbeat_at < ttl:
            continue
        due.append(lease)
    return due


async def _scan_due_sessions() -> None:
    ttl = get_cache_ttl_seconds(MAIN_MODEL)
    due = _due_leases(time.time(), ttl)
    if not due:
        return
    await asyncio.gather(*[_ping_lease(lease) for lease in due])


async def heartbeat_worker() -> None:
    if not HEARTBEAT_ENABLED:
        print("[启动] 缓存心跳未开启")
        return

    ttl = get_cache_ttl_seconds(MAIN_MODEL)
    print(f"[启动] 缓存心跳已开启，间隔={_interval_label(ttl)}")

    scan_interval = _scan_interval_seconds()
    while True:
        try:
            await _scan_due_sessions()
        except Exception as error:
            print(f"[心跳] 扫描异常（将继续）：{error}")
        await asyncio.sleep(scan_interval)
