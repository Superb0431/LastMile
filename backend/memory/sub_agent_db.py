"""子 Agent 使用的独立 SQLite 存储。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import USERS_DIR


def _sub_agent_db_path(username: str) -> Path:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "sub_agent.db"


def _connect(username: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_sub_agent_db_path(username))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sub_agent_messages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id         TEXT    NOT NULL,
            agent_name     TEXT    NOT NULL,
            parent_chat_id TEXT,
            role           TEXT    NOT NULL,
            content        TEXT,
            toolcall_id    TEXT,
            tool_name      TEXT,
            tool_args      TEXT,
            tool_calls     TEXT,
            created_at     TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sub_agent_run "
        "ON sub_agent_messages(run_id, id)"
    )
    return conn


def add_sub_agent_message(
    username: str,
    run_id: str,
    agent_name: str,
    role: str,
    content: Optional[str] = None,
    *,
    parent_chat_id: Optional[str] = None,
    toolcall_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[dict] = None,
    tool_calls: Optional[list] = None,
) -> int:
    tool_args_json = json.dumps(tool_args, ensure_ascii=False) if tool_args is not None else None
    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect(username)
    try:
        cursor = conn.execute(
            """
            INSERT INTO sub_agent_messages
                (run_id, agent_name, parent_chat_id, role, content,
                 toolcall_id, tool_name, tool_args, tool_calls, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                agent_name,
                parent_chat_id,
                role,
                content,
                toolcall_id,
                tool_name,
                tool_args_json,
                tool_calls_json,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def get_sub_agent_messages(username: str, run_id: str) -> list[dict]:
    conn = _connect(username)
    try:
        rows = conn.execute(
            """
            SELECT * FROM sub_agent_messages
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        conn.close()


def rows_to_openai_messages(rows: list[dict]) -> list[dict]:
    messages: list[dict] = []
    for row in rows:
        role = row["role"]
        if role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": row.get("toolcall_id") or "",
                    "content": row.get("content") or "",
                }
            )
        elif role == "assistant" and row.get("tool_calls"):
            messages.append(
                {
                    "role": "assistant",
                    "content": row.get("content") or "",
                    "tool_calls": row["tool_calls"],
                }
            )
        else:
            messages.append({"role": role, "content": row.get("content") or ""})
    return messages


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "agent_name": row["agent_name"],
        "parent_chat_id": row["parent_chat_id"],
        "role": row["role"],
        "content": row["content"],
        "toolcall_id": row["toolcall_id"],
        "tool_name": row["tool_name"],
        "tool_args": json.loads(row["tool_args"]) if row["tool_args"] else None,
        "tool_calls": json.loads(row["tool_calls"]) if row["tool_calls"] else None,
        "created_at": row["created_at"],
    }
