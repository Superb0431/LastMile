"""tool_cache_gateway."""

import json
import logging
from typing import Optional

import redis

from backend.config import REDIS_URL, TOOL_CACHE_DEFAULT_TTL_SECONDS
from backend.memory import db
from backend.tools import registry

logger = logging.getLogger(__name__)

_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def _make_key(username: str, tool_name: str, arguments: Optional[dict]) -> str:
    args_text = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
    return f"{username}::{tool_name}::{args_text}"

def _safe_redis_get(key: str) -> Optional[str]:
    try:
        return _client.get(key)
    except redis.RedisError as error:
        logger.warning("Redis GET 失败，降级为 cache miss：%s", error)
        return None

def _safe_redis_set(key: str, value: str, ttl: int) -> None:
    try:
        _client.setex(key, ttl, value)
    except redis.RedisError as error:
        logger.warning("Redis SETEX 失败，跳过缓存写入：%s", error)

def _should_cache(result: str) -> bool:
    text = result.strip()
    if text.startswith("（") and ("失败" in text or "出错" in text):
        return False
    return True

def execute(
    username: str,
    tool_name: str,
    arguments: dict,
    toolcall_id: str,
) -> str:
    policy = registry.get_cache_policy(tool_name)

    if policy != "redis":
        result = registry.execute_tool(tool_name, arguments, username)
        db.save_tool_result(username, toolcall_id, tool_name, arguments, result)
        return result

    cache_key = _make_key(username, tool_name, arguments)

    cached = _safe_redis_get(cache_key)
    if cached is not None:
        source_id = db.find_source_result_id(username, cache_key)
        db.save_tool_result(
            username,
            toolcall_id,
            tool_name,
            arguments,
            cached,
            from_cache=True,
            cache_key=cache_key,
            source_result_id=source_id,
        )
        return cached

    result = registry.execute_tool(tool_name, arguments, username)

    if _should_cache(result):
        ttl = registry.get_cache_ttl(tool_name) or TOOL_CACHE_DEFAULT_TTL_SECONDS
        _safe_redis_set(cache_key, result, ttl)
        db.save_tool_result(
            username, toolcall_id, tool_name, arguments, result, cache_key=cache_key
        )
    else:
        db.save_tool_result(username, toolcall_id, tool_name, arguments, result)

    return result
