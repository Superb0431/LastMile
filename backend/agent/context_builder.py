"""拼装发给大模型的上下文。"""

import hashlib
import json
from datetime import datetime

from backend.config import EVAL_MODE
from backend.memory import db
from backend.prompts.main_agent import get_system_prompt_with_profile
from backend.agent import dream


def _format_day(created_at: str | None) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        dt = datetime.now()
    return dt.strftime("%Y年%m月%d日")


def _format_prefix_tag(entry: dream.PrefixEntry) -> str:
    return f"[Info_append.{entry.index}]\n{entry.content}\n[/Info_append.{entry.index}]"


def _history_row_to_message(row: dict, prefix: dream.PrefixEntry | None = None) -> dict:
    role = row["role"]
    content = row["content"] or ""

    if role == "tool":
        return {
            "role": "tool",
            "tool_call_id": row["toolcall_id"],
            "content": content,
        }

    if role == "assistant" and row.get("tool_calls"):
        return {
            "role": "assistant",
            "content": content,
            "tool_calls": row["tool_calls"],
        }

    if role == "user":
        if prefix:
            content = _format_prefix_tag(prefix) + "\n\n" + content
        content = f"[当前时间：{_format_day(row.get('created_at'))}]\n{content}"
        return {"role": "user", "content": content}

    return {"role": role, "content": content}


def build_context(chat_id: str, username: str) -> list[dict]:
    state = dream.get_or_init_state(chat_id, username)
    messages: list[dict] = []

    messages.append(
        {
            "role": "system",
            "content": get_system_prompt_with_profile(
                username,
                state.profile_snapshot,
                state.summary,
                eval_mode=EVAL_MODE,
            ),
        }
    )

    history = db.get_messages(chat_id, username, min_id=state.cutoff_msg_id)
    for row in history:
        prefix = dream.find_prefix_for_msg(state, row["id"]) if row["role"] == "user" else None
        messages.append(_history_row_to_message(row, prefix))

    if len(messages) > 1:
        prefix_part = messages[:-1]
    else:
        prefix_part = messages
    print(
        f"[hash02-build_context] 前缀 msgs={len(prefix_part)} "
        f"hash={compute_prefix_hash(prefix_part)}"
    )

    return messages


def build_context_for_deep_dream_summary(chat_id: str, username: str) -> list[dict]:
    state = dream.get_or_init_state(chat_id, username)
    messages: list[dict] = []

    messages.append(
        {
            "role": "system",
            "content": get_system_prompt_with_profile(
                username,
                state.profile_snapshot,
                state.summary,
                eval_mode=EVAL_MODE,
            ),
        }
    )

    summary_cutoff_id = dream.get_summary_cutoff_msg_id(chat_id, username, state)
    if summary_cutoff_id is None:
        return messages

    history = db.get_messages(
        chat_id,
        username,
        min_id=state.cutoff_msg_id,
        max_id_exclusive=summary_cutoff_id,
    )
    for row in history:
        prefix = dream.find_prefix_for_msg(state, row["id"]) if row["role"] == "user" else None
        messages.append(_history_row_to_message(row, prefix))

    return messages


def compute_prefix_hash(messages: list[dict]) -> str:
    serialized = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
