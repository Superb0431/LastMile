"""redis_bus."""

import json
import uuid

import redis

from backend.config import REDIS_URL, TASK_CLAIM_IDLE_MS, TASK_RESULT_TTL_SECONDS

STREAM = "agent:tasks"
GROUP = "agent:workers"

_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_timeout=None,
)

def ensure_group() -> None:
    try:
        _client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as error:
        if "BUSYGROUP" not in str(error):
            raise

def submit_task(chat_id: str, username: str, message: str) -> str:
    task_id = uuid.uuid4().hex
    payload = {
        "task_id": task_id,
        "chat_id": chat_id,
        "username": username,
        "message": message,
    }
    _client.set(f"agent:status:{task_id}", "queued", ex=TASK_RESULT_TTL_SECONDS)
    _client.xadd(STREAM, {"data": json.dumps(payload, ensure_ascii=False)})
    return task_id

def get_status(task_id: str) -> str | None:
    return _client.get(f"agent:status:{task_id}")

def read_events(task_id: str, cursor: int) -> tuple[list[dict], int]:
    key = f"agent:events:{task_id}"
    raw = _client.lrange(key, cursor, -1)
    events = [json.loads(item) for item in raw]
    return events, cursor + len(raw)

def consume(consumer_name: str, block_ms: int = 5000) -> tuple[str, dict] | None:
    try:
        resp = _client.xreadgroup(
            GROUP, consumer_name, {STREAM: ">"}, count=1, block=block_ms
        )
    except redis.TimeoutError:
        return None
    if not resp:
        return None
    _stream, entries = resp[0]
    entry_id, fields = entries[0]
    return entry_id, json.loads(fields["data"])

def claim_stale_tasks(consumer_name: str, count: int = 5) -> list[tuple[str, dict]]:
    try:
        resp = _client.xautoclaim(
            STREAM,
            GROUP,
            consumer_name,
            min_idle_time=TASK_CLAIM_IDLE_MS,
            start_id="0-0",
            count=count,
        )
    except redis.ResponseError:
        return _claim_stale_tasks_legacy(consumer_name, count)

    claimed: list[tuple[str, dict]] = []
    if not resp or len(resp) < 2:
        return claimed
    entries = resp[1]
    for entry_id, fields in entries:
        if not fields:
            continue
        claimed.append((entry_id, json.loads(fields["data"])))
    return claimed

def _claim_stale_tasks_legacy(consumer_name: str, count: int) -> list[tuple[str, dict]]:
    pending = _client.xpending_range(STREAM, GROUP, "-", "+", count)
    stale_ids = [
        item["message_id"]
        for item in pending
        if item.get("time_since_delivered", 0) >= TASK_CLAIM_IDLE_MS
    ]
    if not stale_ids:
        return []
    claimed = _client.xclaim(
        STREAM, GROUP, consumer_name, TASK_CLAIM_IDLE_MS, stale_ids
    )
    result: list[tuple[str, dict]] = []
    for entry_id, fields in claimed:
        result.append((entry_id, json.loads(fields["data"])))
    return result

def push_event(task_id: str, event: dict) -> None:
    key = f"agent:events:{task_id}"
    _client.rpush(key, json.dumps(event, ensure_ascii=False))
    _client.expire(key, TASK_RESULT_TTL_SECONDS)

def set_status(task_id: str, status: str) -> None:
    _client.set(f"agent:status:{task_id}", status, ex=TASK_RESULT_TTL_SECONDS)

def ack(entry_id: str) -> None:
    _client.xack(STREAM, GROUP, entry_id)

def save_profile_snapshot(task_id: str, content: str) -> None:
    _client.set(
        f"agent:profile_snapshot:{task_id}",
        content,
        ex=TASK_RESULT_TTL_SECONDS,
    )

def get_profile_snapshot(task_id: str) -> str | None:
    return _client.get(f"agent:profile_snapshot:{task_id}")
