"""需要用户同意才能执行的工具审批。"""

import asyncio
import time
from typing import Optional

import redis

from backend.config import APPROVAL_TIMEOUT_SECONDS, REDIS_URL

_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

_PENDING_KEY = "agent:approval_pending:{chat_id}"
_ANSWER_KEY = "agent:approval_answer:{chat_id}"


class _RedisWaiter:
    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id

    async def wait(self) -> None:
        deadline = time.monotonic() + APPROVAL_TIMEOUT_SECONDS
        answer_key = _ANSWER_KEY.format(chat_id=self.chat_id)
        while time.monotonic() < deadline:
            if _client.get(answer_key) is not None:
                return
            await asyncio.sleep(0.5)


def create_pending(chat_id: str, toolcall_id: str) -> _RedisWaiter:
    pending_key = _PENDING_KEY.format(chat_id=chat_id)
    answer_key = _ANSWER_KEY.format(chat_id=chat_id)
    _client.delete(answer_key)
    _client.set(
        pending_key,
        toolcall_id,
        ex=APPROVAL_TIMEOUT_SECONDS + 30,
    )
    return _RedisWaiter(chat_id)


def provide_approval(chat_id: str, toolcall_id: str, approved: bool) -> bool:
    pending_key = _PENDING_KEY.format(chat_id=chat_id)
    answer_key = _ANSWER_KEY.format(chat_id=chat_id)
    pending = _client.get(pending_key)
    if pending is None or pending != toolcall_id:
        return False
    _client.set(
        answer_key,
        "yes" if approved else "no",
        ex=APPROVAL_TIMEOUT_SECONDS + 30,
    )
    return True


def get_result(chat_id: str) -> Optional[bool]:
    answer = _client.get(_ANSWER_KEY.format(chat_id=chat_id))
    if answer is None:
        return None
    return answer == "yes"


def clear_pending(chat_id: str) -> None:
    _client.delete(
        _PENDING_KEY.format(chat_id=chat_id),
        _ANSWER_KEY.format(chat_id=chat_id),
    )
