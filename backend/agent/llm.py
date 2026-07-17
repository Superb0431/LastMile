"""llm."""

import json
import time
from typing import AsyncGenerator, Optional

import litellm

from backend.config import MAIN_MODEL, API_KEY, API_BASE
from backend.agent.llm_stats import LLMStats, report, extract_cache_info

LLM_TEXT = "text"
LLM_TOOL_CALLS = "tool_calls"
LLM_DONE = "done"

def _apply_credentials(kwargs: dict, api_key: Optional[str]) -> None:
    key = (api_key if api_key is not None else API_KEY) or None
    if key:
        kwargs["api_key"] = key
    if API_BASE:
        kwargs["api_base"] = API_BASE

async def stream_chat(
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    model: str = MAIN_MODEL,
    *,
    api_key: Optional[str] = None,
    stage: str = "",
    chat_id: str = "",
    username: str = "",
) -> AsyncGenerator[dict, None]:
    kwargs = {
        "model": model,
        "messages": messages,
        "stream": True,
        "extra_body": {"thinking": {"type": "disabled"}},
        "stream_options": {"include_usage": True},
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    _apply_credentials(kwargs, api_key)

    t_start = time.perf_counter()
    t_first_token: Optional[float] = None

    response = await litellm.acompletion(**kwargs)

    tool_calls_buffer: dict[int, dict] = {}
    finish_reason = "stop"
    usage_info = None

    async for chunk in response:
        choice = chunk.choices[0]
        delta = choice.delta

        if getattr(delta, "content", None):
            if t_first_token is None:
                t_first_token = time.perf_counter()
            yield {"type": LLM_TEXT, "text": delta.content}

        if getattr(delta, "tool_calls", None):
            if t_first_token is None:
                t_first_token = time.perf_counter()
            for tc in delta.tool_calls:
                index = tc.index
                entry = tool_calls_buffer.setdefault(
                    index, {"id": "", "name": "", "args": ""}
                )
                if tc.id:
                    entry["id"] = tc.id
                if tc.function and tc.function.name:
                    entry["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    entry["args"] += tc.function.arguments

        if choice.finish_reason:
            finish_reason = choice.finish_reason

        if hasattr(chunk, "usage") and chunk.usage:
            usage_info = chunk.usage

    t_end = time.perf_counter()

    tool_call_count = 0
    if tool_calls_buffer:
        tool_calls = []
        for index in sorted(tool_calls_buffer.keys()):
            entry = tool_calls_buffer[index]
            try:
                arguments = json.loads(entry["args"]) if entry["args"].strip() else {}
            except json.JSONDecodeError:
                arguments = {"_raw": entry["args"], "_parse_error": True}
            tool_calls.append(
                {"id": entry["id"], "name": entry["name"], "arguments": arguments}
            )
        tool_call_count = len(tool_calls)
        yield {"type": LLM_TOOL_CALLS, "tool_calls": tool_calls}

    input_tokens = getattr(usage_info, "prompt_tokens", 0) if usage_info else 0
    output_tokens = getattr(usage_info, "completion_tokens", 0) if usage_info else 0
    cache_hit, cache_miss = extract_cache_info(usage_info)

    stats = LLMStats(
        stage=stage,
        chat_id=chat_id,
        username=username,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit_tokens=cache_hit,
        cache_miss_tokens=cache_miss,
        cache_hit_rate=cache_hit / input_tokens if input_tokens > 0 else 0.0,
        ttft_ms=(t_first_token - t_start) * 1000 if t_first_token else 0.0,
        e2e_latency_ms=(t_end - t_start) * 1000,
        tool_call_count=tool_call_count,
    )
    report(stats)

    yield {"type": LLM_DONE, "finish_reason": finish_reason, "stats": stats}

async def complete(
    messages: list[dict],
    model: str = MAIN_MODEL,
    *,
    api_key: Optional[str] = None,
    tools: Optional[list[dict]] = None,
    stage: str = "",
    chat_id: str = "",
    username: str = "",
) -> str:
    t_start = time.perf_counter()

    completion_kwargs = {
        "model": model,
        "messages": messages,
        "stream": False,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    _apply_credentials(completion_kwargs, api_key)
    if tools:
        completion_kwargs["tools"] = tools
        completion_kwargs["tool_choice"] = "auto"

    response = await litellm.acompletion(**completion_kwargs)

    t_end = time.perf_counter()

    usage_info = getattr(response, "usage", None)
    text = response.choices[0].message.content or ""

    input_tokens = getattr(usage_info, "prompt_tokens", 0) if usage_info else 0
    output_tokens = getattr(usage_info, "completion_tokens", 0) if usage_info else 0
    cache_hit, cache_miss = extract_cache_info(usage_info)

    stats = LLMStats(
        stage=stage,
        chat_id=chat_id,
        username=username,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit_tokens=cache_hit,
        cache_miss_tokens=cache_miss,
        cache_hit_rate=cache_hit / input_tokens if input_tokens > 0 else 0.0,
        ttft_ms=0.0,
        e2e_latency_ms=(t_end - t_start) * 1000,
        tool_call_count=0,
    )
    report(stats)

    return text
