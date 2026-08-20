"""用 SQLite 存聊天消息和相关数据。"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import USERS_DIR


def _user_db_path(username: str) -> Path:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "messages.db"


def _connect_user(username: str) -> sqlite3.Connection:
    conn = sqlite3.connect(_user_db_path(username))
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,  -- 消息编号，从 1 自增
            chat_id     TEXT    NOT NULL,                   -- 属于哪个会话
            username    TEXT    NOT NULL,                   -- 属于哪个用户
            role        TEXT    NOT NULL,                   -- user / assistant / tool
            content     TEXT,                               -- 消息正文
            toolcall_id TEXT,                               -- 工具结果配对 ID（tool 消息用；默认 NULL）
            tool_name   TEXT,                               -- 工具名（tool 消息用；默认 NULL）
            tool_args   TEXT,                               -- 工具参数 JSON（默认 NULL）
            tool_calls  TEXT,                               -- assistant 的整组工具调用 JSON（默认 NULL）
            created_at  TEXT    NOT NULL,                   -- 创建时间
            task_id     TEXT                                -- 异步任务 ID（幂等清理用）
        )
        """
    )
    message_cols = {row["name"] for row in conn.execute("PRAGMA table_info(messages)")}
    if "task_id" not in message_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN task_id TEXT")
    if "tool_calls" not in message_cols:
        conn.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_results (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,  -- 工具结果的唯一 ID
            toolcall_id      TEXT    NOT NULL,                   -- 对应哪一次工具调用
            tool_name        TEXT    NOT NULL,                   -- 工具名
            args             TEXT,                               -- 调用参数 JSON
            result           TEXT,                               -- 工具返回的结果文本
            from_cache       INTEGER NOT NULL DEFAULT 0,         -- 0=真执行 1=命中缓存
            cache_key        TEXT,                               -- 对应的 Redis key
            source_result_id INTEGER,                            -- 命中缓存时指向首次执行的 id
            created_at       TEXT    NOT NULL
        )
        """
    )

    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tool_results)")}
    if "from_cache" not in existing_cols:
        conn.execute("ALTER TABLE tool_results ADD COLUMN from_cache INTEGER NOT NULL DEFAULT 0")
    if "cache_key" not in existing_cols:
        conn.execute("ALTER TABLE tool_results ADD COLUMN cache_key TEXT")
    if "source_result_id" not in existing_cols:
        conn.execute("ALTER TABLE tool_results ADD COLUMN source_result_id INTEGER")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_profile_snapshot (
            chat_id            TEXT PRIMARY KEY,
            profile            TEXT,
            health             TEXT,
            summary            TEXT DEFAULT '',
            cutoff_msg_id      INTEGER,
            prefix_entries_json TEXT DEFAULT '[]',
            next_prefix_index  INTEGER DEFAULT 1,
            pending_info       TEXT,
            updated_at         TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ehr_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_date      TEXT NOT NULL,
            record_date     TEXT NOT NULL,
            diagnosis       TEXT,
            chief_complaint TEXT,
            exam_results    TEXT,
            treatment       TEXT,
            notes           TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS interval_records (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symptom_date TEXT NOT NULL,
            record_date  TEXT NOT NULL,
            symptoms     TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drug_mentions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id  INTEGER NOT NULL,
            chat_id     TEXT NOT NULL,
            drugs       TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
        """
    )

    conn.commit()
    return conn


def init_db() -> None:
    return None


def add_message(
    chat_id: str,
    username: str,
    role: str,
    content: Optional[str],
    toolcall_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[dict] = None,
    tool_calls: Optional[list] = None,
    created_at: Optional[str] = None,
    task_id: Optional[str] = None,
) -> int:

    tool_args_json = json.dumps(tool_args, ensure_ascii=False) if tool_args is not None else None
    tool_calls_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls is not None else None
    now = created_at or datetime.now().isoformat(timespec="seconds")

    conn = _connect_user(username)
    try:
        cursor = conn.execute(
            """
            INSERT INTO messages
                (chat_id, username, role, content, toolcall_id, tool_name, tool_args, tool_calls, created_at, task_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, username, role, content, toolcall_id, tool_name, tool_args_json, tool_calls_json, now, task_id),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_messages(
    chat_id: str,
    username: str,
    min_id: Optional[int] = None,
    max_id_exclusive: Optional[int] = None,
) -> list[dict]:

    conn = _connect_user(username)
    try:
        query = "SELECT * FROM messages WHERE chat_id = ?"
        params: list = [chat_id]
        if min_id is not None:
            query += " AND id >= ?"
            params.append(min_id)
        if max_id_exclusive is not None:
            query += " AND id < ?"
            params.append(max_id_exclusive)
        query += " ORDER BY id ASC"
        rows = conn.execute(query, params).fetchall()
        return [_row_to_message_dict(row) for row in rows]
    finally:
        conn.close()


def search_messages(
    username: str,
    keywords: list[str],
    *,
    roles: tuple[str, ...] = ("user", "assistant"),
    limit: int = 50,
) -> list[dict]:

    cleaned = [kw.strip() for kw in keywords if kw and str(kw).strip()]
    if not cleaned:
        return []
    limit = max(1, min(int(limit), 200))

    conn = _connect_user(username)
    try:
        role_placeholders = ",".join("?" for _ in roles)
        like_clauses = " OR ".join("content LIKE ?" for _ in cleaned)
        sql = f"""
            SELECT id, chat_id, role, content, created_at, tool_calls
            FROM messages
            WHERE role IN ({role_placeholders})
              AND content IS NOT NULL
              AND ({like_clauses})
            ORDER BY id DESC
            LIMIT ?
        """
        params: list = list(roles) + [f"%{kw}%" for kw in cleaned] + [limit]
        rows = conn.execute(sql, params).fetchall()
        results: list[dict] = []
        for row in rows:
            if row["role"] == "assistant" and row["tool_calls"]:
                continue
            content = row["content"] or ""
            matched = next((kw for kw in cleaned if kw in content), cleaned[0])
            results.append(
                {
                    "id": row["id"],
                    "chat_id": row["chat_id"],
                    "role": row["role"],
                    "content": content,
                    "created_at": row["created_at"],
                    "matched_keyword": matched,
                }
            )
        return results
    finally:
        conn.close()


def find_message_background(
    username: str,
    message_id: int,
    k: int = 1,
) -> dict:

    k = max(0, int(k))
    conn = _connect_user(username)
    try:
        anchor_row = conn.execute(
            "SELECT id, chat_id, role, content, created_at, tool_calls FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        if anchor_row is None:
            return {"error": f"未找到 message_id={message_id}", "anchor": None, "turns": []}

        anchor = {
            "id": anchor_row["id"],
            "chat_id": anchor_row["chat_id"],
            "role": anchor_row["role"],
            "content": anchor_row["content"] or "",
            "created_at": anchor_row["created_at"],
        }
        chat_id = anchor["chat_id"]
        rows = conn.execute(
            """
            SELECT id, chat_id, role, content, created_at, tool_calls
            FROM messages
            WHERE chat_id = ? AND role IN ('user', 'assistant')
            ORDER BY id ASC
            """,
            (chat_id,),
        ).fetchall()
        row_dicts = [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"] or "",
                "created_at": row["created_at"],
                "tool_calls": row["tool_calls"],
            }
            for row in rows
        ]
    finally:
        conn.close()

    clean: list[dict] = []
    for row in row_dicts:
        role = row["role"]
        if role == "user":
            clean.append(row)
        elif role == "assistant" and not row["tool_calls"]:
            clean.append(row)

    turns: list[dict] = []
    i = 0
    while i < len(clean):
        if clean[i]["role"] != "user":
            i += 1
            continue
        user_msg = clean[i]
        assistant_msg = None
        j = i + 1
        if j < len(clean) and clean[j]["role"] == "assistant":
            assistant_msg = clean[j]
            j += 1
        turns.append(
            {
                "user": user_msg["content"],
                "assistant": (assistant_msg or {}).get("content", ""),
                "created_at": user_msg["created_at"],
                "user_id": user_msg["id"],
                "assistant_id": (assistant_msg or {}).get("id"),
            }
        )
        i = j

    anchor_idx = None
    for idx, turn in enumerate(turns):
        ids = {turn["user_id"], turn.get("assistant_id")}
        if message_id in ids:
            anchor_idx = idx
            break
    if anchor_idx is None and turns:
        candidates = [i for i, t in enumerate(turns) if t["user_id"] <= message_id]
        anchor_idx = candidates[-1] if candidates else 0

    if anchor_idx is None:
        return {"anchor": anchor, "turns": []}

    start = max(0, anchor_idx - k)
    end = min(len(turns), anchor_idx + k + 1)
    window = turns[start:end]
    return {
        "anchor": anchor,
        "anchor_turn_index": anchor_idx,
        "turns": [
            {
                "user": t["user"],
                "assistant": t["assistant"],
                "created_at": t["created_at"],
            }
            for t in window
        ],
    }


def get_profile_snapshot(username: str, chat_id: str) -> Optional[dict]:
    conn = _connect_user(username)
    try:
        row = conn.execute(
            "SELECT * FROM chat_profile_snapshot WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "chat_id": row["chat_id"],
            "profile": row["profile"] or "",
            "health": row["health"] or "",
            "summary": row["summary"] or "",
            "cutoff_msg_id": row["cutoff_msg_id"],
            "prefix_entries_json": row["prefix_entries_json"] or "[]",
            "next_prefix_index": row["next_prefix_index"] or 1,
            "pending_info": row["pending_info"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


def save_profile_snapshot(
    username: str,
    chat_id: str,
    profile: str,
    summary: str,
    cutoff_msg_id: Optional[int],
    prefix_entries_json: str = "[]",
    next_prefix_index: int = 1,
    pending_info: Optional[str] = None,
    health: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn = _connect_user(username)
    try:
        conn.execute(
            """
            INSERT INTO chat_profile_snapshot
                (chat_id, profile, health, summary, cutoff_msg_id,
                 prefix_entries_json, next_prefix_index, pending_info, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                profile = excluded.profile,
                health = excluded.health,
                summary = excluded.summary,
                cutoff_msg_id = excluded.cutoff_msg_id,
                prefix_entries_json = excluded.prefix_entries_json,
                next_prefix_index = excluded.next_prefix_index,
                pending_info = excluded.pending_info,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                profile,
                health,
                summary,
                cutoff_msg_id,
                prefix_entries_json,
                next_prefix_index,
                pending_info,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def delete_messages_by_task_id(username: str, chat_id: str, task_id: str) -> int:
    if not task_id:
        return 0
    conn = _connect_user(username)
    try:
        cursor = conn.execute(
            "DELETE FROM messages WHERE chat_id = ? AND task_id = ?",
            (chat_id, task_id),
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def list_chats(username: str) -> list[dict]:
    conn = _connect_user(username)
    try:
        rows = conn.execute(
            """
            SELECT chat_id, MAX(created_at) AS last_time
            FROM messages
            GROUP BY chat_id
            ORDER BY last_time DESC
            """
        ).fetchall()
        return [
            {"chat_id": row["chat_id"], "title": row["chat_id"], "last_time": row["last_time"]}
            for row in rows
        ]
    finally:
        conn.close()


def save_tool_result(
    username: str,
    toolcall_id: str,
    tool_name: str,
    args: Optional[dict],
    result: str,
    from_cache: bool = False,
    cache_key: Optional[str] = None,
    source_result_id: Optional[int] = None,
) -> int:


    args_json = json.dumps(args, ensure_ascii=False) if args is not None else None
    now = datetime.now().isoformat(timespec="seconds")

    conn = _connect_user(username)
    try:
        cursor = conn.execute(
            """
            INSERT INTO tool_results
                (toolcall_id, tool_name, args, result,
                 from_cache, cache_key, source_result_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                toolcall_id,
                tool_name,
                args_json,
                result,
                1 if from_cache else 0,
                cache_key,
                source_result_id,
                now,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def find_source_result_id(username: str, cache_key: str) -> Optional[int]:
    conn = _connect_user(username)
    try:
        row = conn.execute(
            """
            SELECT id FROM tool_results
            WHERE cache_key = ? AND from_cache = 0
            ORDER BY id DESC LIMIT 1
            """,
            (cache_key,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_tool_result(username: str, toolcall_id: str) -> Optional[dict]:
    conn = _connect_user(username)
    try:
        row = conn.execute(
            "SELECT * FROM tool_results WHERE toolcall_id = ? ORDER BY id DESC LIMIT 1",
            (toolcall_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "toolcall_id": row["toolcall_id"],
            "tool_name": row["tool_name"],
            "args": json.loads(row["args"]) if row["args"] else None,
            "result": row["result"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def add_ehr_record(
    username: str,
    visit_date: str,
    diagnosis: str = "",
    chief_complaint: str = "",
    exam_results: str = "",
    treatment: str = "",
    notes: str = "",
    record_date: Optional[str] = None,
) -> int:
    conn = _connect_user(username)
    try:
        cursor = conn.execute(
            """
            INSERT INTO ehr_records
                (visit_date, record_date, diagnosis, chief_complaint,
                 exam_results, treatment, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                visit_date,
                record_date or _now_iso(),
                diagnosis or "未知",
                chief_complaint,
                exam_results,
                treatment,
                notes,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def add_interval_record(
    username: str,
    symptom_date: str,
    symptoms: str,
    record_date: Optional[str] = None,
) -> int:
    conn = _connect_user(username)
    try:
        cursor = conn.execute(
            """
            INSERT INTO interval_records (symptom_date, record_date, symptoms)
            VALUES (?, ?, ?)
            """,
            (symptom_date, record_date or _now_iso(), symptoms),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def list_ehr_records(username: str) -> list[dict]:
    conn = _connect_user(username)
    try:
        rows = conn.execute(
            "SELECT * FROM ehr_records ORDER BY id ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_interval_records(username: str) -> list[dict]:
    conn = _connect_user(username)
    try:
        rows = conn.execute(
            "SELECT * FROM interval_records ORDER BY id ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_drug_mentions(
    username: str,
    message_id: int,
    chat_id: str,
    drugs: list[str],
) -> None:
    if not drugs:
        return

    now = _now_iso()
    conn = _connect_user(username)
    try:
        conn.execute(
            """
            INSERT INTO drug_mentions (message_id, chat_id, drugs, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (message_id, chat_id, json.dumps(drugs, ensure_ascii=False), now),
        )
        conn.commit()
    finally:
        conn.close()


def get_drug_mentions(username: str, message_id: int) -> list[str]:
    conn = _connect_user(username)
    try:
        row = conn.execute(
            """
            SELECT drugs FROM drug_mentions
            WHERE message_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["drugs"] or "[]")
    finally:
        conn.close()


def format_timeline_text(username: str) -> str:
    ehr_rows = list_ehr_records(username)
    interval_rows = list_interval_records(username)
    if not ehr_rows and not interval_rows:
        return ""

    lines: list[str] = []
    if ehr_rows:
        lines.append("【就诊记录 EHR】")
        for row in ehr_rows:
            lines.append(
                f"- 到院日期：{row['visit_date']} | 记录日期：{row['record_date']}\n"
                f"  诊断：{row['diagnosis'] or '未知'}\n"
                f"  主诉：{row['chief_complaint'] or '（无）'}\n"
                f"  检查结果：{row['exam_results'] or '（无）'}\n"
                f"  医生处置：{row['treatment'] or '（无）'}\n"
                f"  备注：{row['notes'] or '（无）'}"
            )
    if interval_rows:
        lines.append("【症状记录 Interval】")
        for row in interval_rows:
            lines.append(
                f"- 日期：{row['symptom_date']} | 记录日期：{row['record_date']}\n"
                f"  症状：{row['symptoms']}"
            )
    return "\n".join(lines)


def _row_to_message_dict(row: sqlite3.Row) -> dict:
    row_keys = row.keys()
    tool_calls_raw = row["tool_calls"] if "tool_calls" in row_keys else None
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "username": row["username"],
        "role": row["role"],
        "content": row["content"],
        "toolcall_id": row["toolcall_id"],
        "tool_name": row["tool_name"],
        "tool_args": json.loads(row["tool_args"]) if row["tool_args"] else None,
        "tool_calls": json.loads(tool_calls_raw) if tool_calls_raw else None,
        "created_at": row["created_at"],
        "task_id": row["task_id"] if "task_id" in row_keys else None,
    }
