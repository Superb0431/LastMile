"""检索并阅读医学文档。"""

from backend.sub_agents.docs_agent import run_docs_agent


def run_read_docs(query: str) -> str:
    return run_docs_agent(query)
