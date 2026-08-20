"""阅读医学文档的子 Agent。"""

from __future__ import annotations

import json
import sqlite3

import litellm

from backend.config import DOCS_AGENT_API_BASE, DOCS_AGENT_API_KEY, DOCS_AGENT_MODEL, DOCS_INDEX_DB_PATH

DOCS_AGENT_SYSTEM_PROMPT = """
你是一位医学指南检索分析助手。
根据用户查询，阅读候选指南片段，输出：
1) 与查询最相关的分析结论（简洁、可引用）
2) 使用了哪些文档片段（doc_id、章节）

只基于给定片段作答，不要编造未出现的诊断标准或治疗建议。
输出 JSON：
{
  "analysis": "...",
  "doc_refs": [{"doc_id": "...", "title": "...", "section": "..."}]
}
""".strip()


def _search_docs(query: str, limit: int = 5) -> list[dict]:
    if not DOCS_INDEX_DB_PATH.exists():
        return []
    conn = sqlite3.connect(DOCS_INDEX_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT doc_id, title, section, content, source
            FROM docs_fts
            WHERE docs_fts MATCH ?
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def docs_agent_llm_call(messages: list[dict]) -> str:
    kwargs: dict = {
        "model": DOCS_AGENT_MODEL,
        "messages": messages,
        "api_key": DOCS_AGENT_API_KEY or None,
    }
    if DOCS_AGENT_API_BASE:
        kwargs["api_base"] = DOCS_AGENT_API_BASE
    response = litellm.completion(**kwargs)
    return response.choices[0].message.content or ""


def run_docs_agent(query: str) -> str:
    hits = _search_docs(query)
    if not hits:
        return json.dumps(
            {
                "analysis": "未找到相关指南内容。",
                "doc_refs": [],
            },
            ensure_ascii=False,
        )

    context_lines = []
    for item in hits:
        context_lines.append(
            f"[doc_id={item['doc_id']}] {item['title']} / {item['section']}\n{item['content']}"
        )
    user_content = (
        f"用户查询：{query}\n\n"
        "候选指南片段：\n"
        + "\n\n---\n\n".join(context_lines)
    )
    messages = [
        {"role": "system", "content": DOCS_AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    raw = docs_agent_llm_call(messages).strip()
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        return json.dumps(
            {
                "analysis": raw,
                "doc_refs": [
                    {"doc_id": h["doc_id"], "title": h["title"], "section": h["section"]}
                    for h in hits[:3]
                ],
            },
            ensure_ascii=False,
        )
