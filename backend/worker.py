"""worker."""

import asyncio
from pathlib import Path

from backend.config import USERS_DIR, WORKER_COUNT, ensure_dirs
from backend.memory import db
from backend.agent.agent_loop import run_agent_turn
from backend.agent.events import EVENT_DONE, EVENT_ERROR, make_event
from backend.queue import redis_bus

def _profile_path(username: str) -> Path:
    return USERS_DIR / username / "profile.md"

def _prepare_task(task_id: str, username: str, chat_id: str, *, is_retry: bool) -> None:
    profile_path = _profile_path(username)
    if is_retry:
        saved = redis_bus.get_profile_snapshot(task_id)
        if saved is not None:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            profile_path.write_text(saved, encoding="utf-8")
        db.delete_messages_by_task_id(username, chat_id, task_id)
        return

    if profile_path.exists():
        redis_bus.save_profile_snapshot(task_id, profile_path.read_text(encoding="utf-8"))
    else:
        redis_bus.save_profile_snapshot(task_id, "")

async def _run_one(
    task_id: str,
    chat_id: str,
    username: str,
    message: str,
    *,
    is_retry: bool = False,
) -> None:
    _prepare_task(task_id, username, chat_id, is_retry=is_retry)
    redis_bus.set_status(task_id, "running")
    try:
        async for event in run_agent_turn(
            chat_id, username, message, task_id=task_id
        ):
            redis_bus.push_event(task_id, event)
        redis_bus.set_status(task_id, "done")
    except Exception as error:
        print(f"[Worker] 任务 {task_id} 异常：{error}")
        redis_bus.push_event(task_id, make_event(EVENT_ERROR, message=f"出错了：{error}"))
        redis_bus.push_event(task_id, make_event(EVENT_DONE, chat_id=chat_id))
        redis_bus.set_status(task_id, "error")

async def _process_task(entry_id: str, payload: dict, *, is_retry: bool) -> None:
    task_id = payload["task_id"]
    print(f"[Worker] 处理任务 {task_id}{'（认领重试）' if is_retry else ''}")
    await _run_one(
        task_id,
        payload["chat_id"],
        payload["username"],
        payload["message"],
        is_retry=is_retry,
    )
    redis_bus.ack(entry_id)
    print(f"[Worker] 任务 {task_id} 完成并 ACK")

async def _worker(name: str) -> None:
    print(f"[Worker {name}] 上线，等待任务…")
    while True:
        stale = await asyncio.to_thread(redis_bus.claim_stale_tasks, name)
        for entry_id, payload in stale:
            await _process_task(entry_id, payload, is_retry=True)

        got = await asyncio.to_thread(redis_bus.consume, name, 5000)
        if got is None:
            continue
        entry_id, payload = got
        await _process_task(entry_id, payload, is_retry=False)

async def main() -> None:
    ensure_dirs()
    db.init_db()
    redis_bus.ensure_group()
    await asyncio.gather(*[_worker(f"worker-{i + 1}") for i in range(WORKER_COUNT)])

if __name__ == "__main__":
    asyncio.run(main())
