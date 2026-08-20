"""跨会话回忆历史对话的工具入口。"""

from backend.sub_agents.history_agent import run_history_agent


def run_recall_history(request: str, recent_dialogue: str = "", username: str = "") -> str:
    return run_history_agent(request, recent_dialogue or "", username)
