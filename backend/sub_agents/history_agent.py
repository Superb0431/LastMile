"""跨会话检索历史对话的子 Agent。"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import litellm
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.config import (
    HISTORY_AGENT_API_BASE,
    HISTORY_AGENT_API_KEY,
    HISTORY_AGENT_MAX_TOOL_CALLS,
    HISTORY_AGENT_MODEL,
)
from backend.memory import db
from backend.memory import sub_agent_db
from backend.prompts.history_agent import get_history_agent_system_prompt

AGENT_NAME = "history"


class GrepArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    keywords: list[str] = Field(min_length=1, description="检索关键词列表")
    limit: int = Field(default=50, ge=1, le=200, description="最多返回条数")


class FindBackgroundArgs(BaseModel):
    model_config = ConfigDict(strict=False, extra="forbid")
    message_id: int = Field(description="grep 命中条目的消息 id")
    k: int = Field(default=1, ge=0, le=5, description="前后各几对用户-助手对话，默认 1")


_INTERNAL_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": (
                "在用户全部会话的聊天消息中按关键词搜索（user/assistant）。"
                "传入 1～5 个具体关键词，返回匹配条目列表。"
            ),
            "parameters": GrepArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_background",
            "description": (
                "以某条消息 id 为锚点，返回同会话前后各 k 对用户-助手对话原文。"
            ),
            "parameters": FindBackgroundArgs.model_json_schema(),
        },
    },
]


def _run_grep(username: str, arguments: dict) -> str:
    try:
        args = GrepArgs.model_validate(arguments)
    except ValidationError as e:
        return f"（参数错误：{e}）"
    hits = db.search_messages(username, args.keywords, limit=args.limit)
    if not hits:
        return json.dumps({"hits": [], "note": "未找到匹配消息"}, ensure_ascii=False)
    slim = []
    for h in hits:
        content = h["content"]
        if len(content) > 500:
            content = content[:500] + "…"
        slim.append({**h, "content": content})
    return json.dumps({"hits": slim, "count": len(slim)}, ensure_ascii=False)


def _run_find_background(username: str, arguments: dict) -> str:
    try:
        args = FindBackgroundArgs.model_validate(arguments)
    except ValidationError as e:
        return f"（参数错误：{e}）"
    result = db.find_message_background(username, args.message_id, k=args.k)
    return json.dumps(result, ensure_ascii=False)


def _execute_internal_tool(username: str, name: str, arguments: dict) -> str:
    if name == "grep":
        return _run_grep(username, arguments)
    if name == "find_background":
        return _run_find_background(username, arguments)
    return f"（未知工具：{name}）"


def _history_llm_call(messages: list[dict], *, tools: Optional[list[dict]] = None) -> Any:
    kwargs: dict = {
        "model": HISTORY_AGENT_MODEL,
        "messages": messages,
        "api_key": HISTORY_AGENT_API_KEY or None,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    if HISTORY_AGENT_API_BASE:
        kwargs["api_base"] = HISTORY_AGENT_API_BASE
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    response = litellm.completion(**kwargs)
    return response.choices[0].message


def _parse_tool_calls(message: Any) -> list[dict]:
    raw = getattr(message, "tool_calls", None) or []
    parsed: list[dict] = []
    for tc in raw:
        fn = tc.function
        args_raw = fn.arguments or "{}"
        try:
            arguments = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except json.JSONDecodeError:
            arguments = {}
        parsed.append(
            {
                "id": tc.id,
                "name": fn.name,
                "arguments": arguments,
            }
        )
    return parsed


def _make_assistant_tool_message(content: Optional[str], tool_calls: list[dict]) -> dict:
    return {
        "role": "assistant",
        "content": content or "",
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


def _persist(
    username: str,
    run_id: str,
    role: str,
    content: Optional[str] = None,
    *,
    parent_chat_id: Optional[str] = None,
    toolcall_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[dict] = None,
    tool_calls: Optional[list] = None,
) -> None:
    sub_agent_db.add_sub_agent_message(
        username,
        run_id,
        AGENT_NAME,
        role,
        content,
        parent_chat_id=parent_chat_id,
        toolcall_id=toolcall_id,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_calls=tool_calls,
    )


def _normalize_final(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return json.dumps(
            {"summary": "子 Agent 未返回有效内容。", "quotes": []},
            ensure_ascii=False,
        )
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "summary" in data:
            data.setdefault("quotes", [])
            return json.dumps(data, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    return json.dumps({"summary": raw, "quotes": []}, ensure_ascii=False)


def run_history_agent(
    request: str,
    recent_dialogue: str,
    username: str,
    *,
    parent_chat_id: Optional[str] = None,
) -> str:
    run_id = uuid.uuid4().hex
    user_content = (
        "【主Agent检索请求】\n"
        + request.strip()
        + "\n\n【当前对话与近两轮上下文】\n"
        + (recent_dialogue or "（未提供）").strip()
    )

    messages: list[dict] = [
        {"role": "system", "content": get_history_agent_system_prompt()},
        {"role": "user", "content": user_content},
    ]
    _persist(
        username, run_id, "system", messages[0]["content"], parent_chat_id=parent_chat_id
    )
    _persist(
        username, run_id, "user", messages[1]["content"], parent_chat_id=parent_chat_id
    )

    tool_call_count = 0
    final_text = ""

    while True:
        message = _history_llm_call(messages, tools=_INTERNAL_TOOLS)
        assistant_text = (message.content or "").strip()
        pending = _parse_tool_calls(message)

        if not pending:
            final_text = assistant_text
            _persist(
                username,
                run_id,
                "assistant",
                final_text,
                parent_chat_id=parent_chat_id,
            )
            break

        assistant_msg = _make_assistant_tool_message(assistant_text, pending)
        messages.append(assistant_msg)
        _persist(
            username,
            run_id,
            "assistant",
            assistant_text,
            parent_chat_id=parent_chat_id,
            tool_calls=assistant_msg["tool_calls"],
        )

        for tc in pending:
            tool_call_count += 1
            name = tc["name"]
            arguments = tc["arguments"] if isinstance(tc["arguments"], dict) else {}
            print(
                f"[history_agent] run={run_id[:8]} 工具 {name} "
                f"args={json.dumps(arguments, ensure_ascii=False)[:80]}"
            )
            result_text = _execute_internal_tool(username, name, arguments)
            print(f"[history_agent] 工具结果 {name}: {result_text[:120]}")
            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": result_text}
            )
            _persist(
                username,
                run_id,
                "tool",
                result_text,
                parent_chat_id=parent_chat_id,
                toolcall_id=tc["id"],
                tool_name=name,
                tool_args=arguments,
            )

        if tool_call_count >= HISTORY_AGENT_MAX_TOOL_CALLS:
            cap_msg = {
                "role": "user",
                "content": (
                    "（系统提示：工具调用次数已达上限，请不要再调用工具，"
                    "直接根据已有检索结果输出最终 JSON。）"
                ),
            }
            messages.append(cap_msg)
            _persist(
                username,
                run_id,
                "user",
                cap_msg["content"],
                parent_chat_id=parent_chat_id,
            )
            message = _history_llm_call(messages, tools=None)
            final_text = (message.content or "").strip()
            _persist(
                username,
                run_id,
                "assistant",
                final_text,
                parent_chat_id=parent_chat_id,
            )
            break

    return _normalize_final(final_text)
