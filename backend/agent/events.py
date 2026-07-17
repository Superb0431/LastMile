"""events."""

import json

EVENT_TOKEN = "token"
EVENT_TOOL_CALL = "tool_call"
EVENT_APPROVAL_REQUEST = "approval_request"
EVENT_TOOL_RESULT = "tool_result"
EVENT_CHAT_INFO = "chat_info"
EVENT_DONE = "done"
EVENT_ERROR = "error"
EVENT_SAFETY_FLAG = "safety_flag"

def make_event(event_type: str, **data) -> dict:
    return {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False),
    }
