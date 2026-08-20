"""对话结束后整理记忆并在需要时压缩上下文。"""

from __future__ import annotations

import json
import litellm
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from backend.config import MAIN_MODEL, MODEL_CONTEXT_WINDOW, USERS_DIR, LIGHT_DREAM_MODEL, DEEPSEEK_LIGHT_DREAM_API_KEY, EVAL_MODE
from backend.agent import llm
from backend.memory import db
from backend.tools import registry
from backend.prompts.light_dream import (
    get_light_dream_system_prompt,
    build_light_dream_task_instruction,
)
from backend.prompts.deep_dream import get_deep_dream_summary_instruction

DEEP_DREAM_KEEP_USER_MSGS = 3
PREFIX_COUNT_THRESHOLD = 12
PREFIX_USER_MSG_SPAN_THRESHOLD = 20
LIGHT_DREAM_RECENT_TURNS = 2


def _format_dialogue_day(created_at: str | None) -> str:
    try:
        dt = datetime.fromisoformat(created_at)
    except (TypeError, ValueError):
        dt = datetime.now()
    return dt.strftime("%Y年%m月%d日")


def _resolve_dialogue_date(turns: list[dict]) -> str:
    for row in reversed(turns):
        if row.get("role") != "user":
            continue
        created_at = row.get("created_at")
        if not created_at:
            continue
        try:
            return datetime.fromisoformat(created_at).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return str(created_at)[:10]
    return ""


def _is_vague_record_date(value: str) -> bool:
    v = (value or "").strip()
    return not v or v == "不确定"


def _apply_write_record_date_fallback(arguments: dict, dialogue_date: str) -> dict:
    if not dialogue_date:
        return arguments

    args = dict(arguments)
    target = (args.get("target") or "").strip().lower()

    if target == "interval" and _is_vague_record_date(args.get("symptom_date", "")):
        args["symptom_date"] = dialogue_date
    if target == "ehr" and _is_vague_record_date(args.get("visit_date", "")):
        args["visit_date"] = dialogue_date
    if target in ("interval", "ehr") and EVAL_MODE and not (args.get("record_date") or "").strip():
        args["record_date"] = dialogue_date

    return args


@dataclass
class PrefixEntry:
    index: int
    content: str
    target_msg_id: int
    user_msg_position: int
    byte_count: int


@dataclass
class ChatDreamState:
    prefix_entries: list[PrefixEntry] = field(default_factory=list)
    next_prefix_index: int = 1
    pending_info: Optional[str] = None
    profile_snapshot: str = ""
    summary: str = ""
    cutoff_msg_id: Optional[int] = None


_chat_states: dict[str, ChatDreamState] = {}


def _read_user_file(username: str, filename: str) -> str:
    file_path = USERS_DIR / username / filename
    if not file_path.exists():
        return ""
    return file_path.read_text(encoding="utf-8").strip()


def _serialize_prefix_entries(entries: list[PrefixEntry]) -> str:
    return json.dumps([asdict(e) for e in entries], ensure_ascii=False)


def _deserialize_prefix_entries(data: str) -> list[PrefixEntry]:
    if not data:
        return []
    items = json.loads(data)
    return [
        PrefixEntry(
            index=item["index"],
            content=item["content"],
            target_msg_id=item["target_msg_id"],
            user_msg_position=item["user_msg_position"],
            byte_count=item["byte_count"],
        )
        for item in items
    ]


def _persist_state(username: str, chat_id: str, state: ChatDreamState) -> None:
    db.save_profile_snapshot(
        username=username,
        chat_id=chat_id,
        profile=state.profile_snapshot,
        summary=state.summary,
        cutoff_msg_id=state.cutoff_msg_id,
        prefix_entries_json=_serialize_prefix_entries(state.prefix_entries),
        next_prefix_index=state.next_prefix_index,
        pending_info=state.pending_info,
    )


def get_or_init_state(chat_id: str, username: str) -> ChatDreamState:
    if chat_id in _chat_states:
        return _chat_states[chat_id]

    snapshot = db.get_profile_snapshot(username, chat_id)
    if snapshot:
        state = ChatDreamState(
            profile_snapshot=snapshot["profile"],
            summary=snapshot["summary"],
            cutoff_msg_id=snapshot["cutoff_msg_id"],
            prefix_entries=_deserialize_prefix_entries(snapshot["prefix_entries_json"]),
            next_prefix_index=snapshot["next_prefix_index"],
            pending_info=snapshot["pending_info"],
        )
    else:
        profile = _read_user_file(username, "profile.md")
        state = ChatDreamState(profile_snapshot=profile)
        _persist_state(username, chat_id, state)

    _chat_states[chat_id] = state
    return state


def find_prefix_for_msg(state: ChatDreamState, msg_id: int) -> Optional[PrefixEntry]:
    for entry in state.prefix_entries:
        if entry.target_msg_id == msg_id:
            return entry
    return None


def inject_pending_prefix(chat_id: str, username: str, latest_user_msg_id: int) -> None:
    state = get_or_init_state(chat_id, username)
    if not state.pending_info:
        return

    history = db.get_messages(chat_id, username, min_id=state.cutoff_msg_id)
    user_msg_position = sum(1 for m in history if m["role"] == "user" and m["id"] <= latest_user_msg_id)

    content = state.pending_info
    entry = PrefixEntry(
        index=state.next_prefix_index,
        content=content,
        target_msg_id=latest_user_msg_id,
        user_msg_position=user_msg_position,
        byte_count=len(content.encode("utf-8")),
    )
    state.prefix_entries.append(entry)
    state.next_prefix_index += 1
    state.pending_info = None

    _write_prefix_history(username, chat_id, entry)
    _persist_state(username, chat_id, state)


def _write_prefix_history(username: str, chat_id: str, entry: PrefixEntry) -> None:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    history_path = user_dir / "prefix_history.md"
    is_new = not history_path.exists() or history_path.stat().st_size == 0
    with open(history_path, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {username} prefix 历史记录\n\n")
        f.write(f"\n## [Info_append.{entry.index}]\n")
        f.write(
            f"<!-- chat_id={chat_id} | bytes={entry.byte_count} | "
            f"target_msg_id={entry.target_msg_id} | user_msg_position={entry.user_msg_position} -->\n"
        )
        f.write(f"{entry.content}\n")


def _prefix_user_msg_span(state: ChatDreamState) -> int:
    if not state.prefix_entries:
        return 0
    positions = [e.user_msg_position for e in state.prefix_entries]
    return max(positions) - min(positions)


def get_summary_cutoff_msg_id(chat_id: str, username: str, state: ChatDreamState) -> Optional[int]:
    history = db.get_messages(chat_id, username, min_id=state.cutoff_msg_id)
    user_msg_ids = [m["id"] for m in history if m["role"] == "user"]
    if not user_msg_ids:
        return None
    if len(user_msg_ids) >= DEEP_DREAM_KEEP_USER_MSGS:
        return user_msg_ids[-DEEP_DREAM_KEEP_USER_MSGS]
    return user_msg_ids[0]


def should_deep_dream(chat_id: str, username: str, model: str = MAIN_MODEL) -> bool:
    state = get_or_init_state(chat_id, username)

    if len(state.prefix_entries) >= PREFIX_COUNT_THRESHOLD:
        return True
    if _prefix_user_msg_span(state) > PREFIX_USER_MSG_SPAN_THRESHOLD:
        return True

    from backend.agent.context_builder import build_context

    messages = build_context(chat_id, username)
    try:
        total_tokens = litellm.token_counter(model=model, messages=messages)
    except Exception:
        text_len = sum(len(str(m.get("content", ""))) for m in messages)
        total_tokens = text_len // 4

    threshold = MODEL_CONTEXT_WINDOW * 0.30
    return total_tokens > threshold


def _collect_recent_turns(
    chat_id: str, username: str, n_turns: int = LIGHT_DREAM_RECENT_TURNS
) -> list[dict]:
    state = get_or_init_state(chat_id, username)
    history = db.get_messages(chat_id, username, min_id=state.cutoff_msg_id)
    user_ids = [m["id"] for m in history if m["role"] == "user"]
    if not user_ids:
        return []

    start_user_ids = user_ids[-n_turns:] if len(user_ids) >= n_turns else user_ids
    start_id = start_user_ids[0]

    clean: list[dict] = []
    for row in history:
        if row["id"] < start_id:
            continue
        role = row["role"]
        if role == "user":
            clean.append(row)
        elif role == "assistant" and not row.get("toolcall_id") and not row.get("tool_calls"):
            clean.append(row)
    return clean


def _render_recent_turns(
    chat_id: str, username: str, n_turns: int = LIGHT_DREAM_RECENT_TURNS
) -> str:
    turns = _collect_recent_turns(chat_id, username, n_turns)
    if not turns:
        return "【近两轮对话】\n（暂无近期对话。）"

    lines = ["【近两轮对话】"]
    for row in turns:
        label = "用户" if row["role"] == "user" else "助手"
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if row["role"] == "user":
            day = _format_dialogue_day(row.get("created_at"))
            content = f"[当前时间：{day}]\n{content}"
        lines.append(f"{label}：{content}")
    return "\n\n".join(lines)

def _build_light_dream_messages(chat_id: str, username: str) -> list[dict]:
    profile_block = _read_user_file(username, "profile.md") or "（暂无用户画像记录。）"
    recent = _collect_recent_turns(chat_id, username)
    dialogue_date = _resolve_dialogue_date(recent)
    recent_dialogue = _render_recent_turns(chat_id, username)
    return [
        {"role": "system", "content": get_light_dream_system_prompt(eval_mode=EVAL_MODE)},
        {
            "role": "user",
            "content": build_light_dream_task_instruction(
                recent_dialogue, profile_block, dialogue_date=dialogue_date
            ),
        },
    ]

def _make_assistant_tool_message(assistant_text: str, tool_calls: list[dict]) -> dict:
    return {
        "role": "assistant",
        "content": assistant_text,
        "tool_calls": [
            {
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ],
    }


async def _run_light_dream_react(
    chat_id: str, username: str, messages: list[dict], dialogue_date: str = ""
) -> tuple[str, list[str]]:

    messages = list(messages)

    tools = registry.get_light_dream_tools()
    tool_call_count = 0
    light_call_index = 0
    profile_writes: list[str] = []
    final_text = ""

    while True:
        assistant_text = ""
        pending_tool_calls: list[dict] = []

        light_call_index += 1
        async for piece in llm.stream_chat(
            messages,
            tools=tools,
            model=LIGHT_DREAM_MODEL,
            api_key=DEEPSEEK_LIGHT_DREAM_API_KEY,
            stage=f"LightDream第{light_call_index}次调用",
            chat_id=chat_id,
            username=username,
        ):
            if piece["type"] == llm.LLM_TEXT:
                assistant_text += piece["text"]
            elif piece["type"] == llm.LLM_TOOL_CALLS:
                pending_tool_calls = piece["tool_calls"]

        if not pending_tool_calls:
            final_text = assistant_text.strip()
            break

        messages.append(_make_assistant_tool_message(assistant_text, pending_tool_calls))

        for tool_call in pending_tool_calls:
            tool_call_count += 1
            name = tool_call["name"]
            arguments = tool_call["arguments"]
            toolcall_id = tool_call["id"]

            print(
                f"[light_dream] 工具调用 {name} "
                f"args={json.dumps(arguments, ensure_ascii=False)[:80]}"
            )

            ok, reason = registry.if_valid(tool_call, mode="light_dream")
            if not ok:
                result_text = f"（工具调用格式有误：{reason}）"
            else:
                ok, reason = registry.check_arguments(name, arguments)
                if not ok:
                    result_text = f"（工具参数不合法：{reason}）"
                else:
                    if name == "write_record":
                        arguments = _apply_write_record_date_fallback(arguments, dialogue_date)
                    result_text = registry.execute_tool(name, arguments, username)
                    if name == "write_record":
                        target = (arguments.get("target") or "").strip().lower()
                        content = (arguments.get("content") or "").strip()
                        if (
                            target == "profile"
                            and content
                            and not result_text.startswith("（")
                        ):
                            profile_writes.append(content)

            print(f"[light_dream] 工具结果 {name}: {result_text[:100]}")
            messages.append({"role": "tool", "tool_call_id": toolcall_id, "content": result_text})

        if tool_call_count >= registry.LIGHT_DREAM_MAX_TOOL_CALLS:
            messages.append(
                {
                    "role": "user",
                    "content": "（系统提示：工具调用次数已达上限，请直接给出整理总结或回复「无」。）",
                }
            )
            final_text = (
                await llm.complete(
                    messages,
                    model=LIGHT_DREAM_MODEL,
                    api_key=DEEPSEEK_LIGHT_DREAM_API_KEY,
                    stage=f"LightDream第{light_call_index}次调用",
                    chat_id=chat_id,
                    username=username,
                )
            ).strip()
            break

    return final_text, profile_writes


async def light_dream(chat_id: str, username: str) -> None:
    try:
        print(f"[light_dream] 开始 chat={chat_id} user={username}")

        recent = _collect_recent_turns(chat_id, username)
        if not recent:
            print("[light_dream] 无近期对话，跳过")
            return

        messages = _build_light_dream_messages(chat_id, username)
        dialogue_date = _resolve_dialogue_date(recent)
        print(f"[light_dream] 独立上下文 messages={len(messages)} recent_turns={len(recent)}")

        summary, profile_writes = await _run_light_dream_react(
            chat_id, username, messages, dialogue_date=dialogue_date
        )
        print(
            f"[light_dream] 完成，profile_writes={len(profile_writes)} "
            f"总结={summary[:80] if summary else '（空）'}"
        )

        state = get_or_init_state(chat_id, username)
        if profile_writes:
            state.pending_info = "\n".join(profile_writes)
        _persist_state(username, chat_id, state)

    except Exception as error:
        print(f"[light_dream] 整理记忆时出错（已忽略）：{error}")


async def deep_dream(chat_id: str, username: str) -> None:
    state = get_or_init_state(chat_id, username)
    summary_cutoff_id = get_summary_cutoff_msg_id(chat_id, username, state)

    from backend.agent.context_builder import build_context_for_deep_dream_summary

    summary_messages = build_context_for_deep_dream_summary(chat_id, username)
    if len(summary_messages) > 1:
        summary_messages.append(
            {
                "role": "user",
                "content": get_deep_dream_summary_instruction(eval_mode=EVAL_MODE),
            }
        )
        summary_text = (
            await llm.complete(
                summary_messages,
                model=MAIN_MODEL,
                tools=registry.get_initial_tools(),
                stage="DeepDream",
                chat_id=chat_id,
                username=username,
            )
        ).strip()
        if not summary_text:
            summary_text = state.summary
            print("[deep_dream] 摘要为空，保留旧 summary")
    else:
        summary_text = state.summary

    state.profile_snapshot = _read_user_file(username, "profile.md")
    state.summary = summary_text
    state.cutoff_msg_id = summary_cutoff_id
    state.prefix_entries.clear()
    state.next_prefix_index = 1
    state.pending_info = None

    _persist_state(username, chat_id, state)
    print(f"[deep_dream] 完成 chat={chat_id} cutoff={summary_cutoff_id}")
