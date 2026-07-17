"""read_record."""

from pathlib import Path

from backend.config import USERS_DIR
from backend.memory import db

def _read_profile_file(username: str) -> str:
    path = USERS_DIR / username / "profile.md"
    if not path.exists():
        return "（暂无用户画像记录。）"
    return path.read_text(encoding="utf-8").strip() or "（暂无用户画像记录。）"

def run_read_record(username: str, target: str = "all", recent_n: int | None = None) -> str:
    target = (target or "all").strip().lower()
    parts: list[str] = []

    if target in ("profile", "all"):
        parts.append("【用户画像 Profile】\n" + _read_profile_file(username))

    if target in ("ehr", "all"):
        rows = db.list_ehr_records(username)
        if recent_n is not None and rows:
            rows = rows[-recent_n:]
        if not rows:
            parts.append("【就诊记录 EHR】\n（暂无就诊记录。）")
        else:
            lines = ["【就诊记录 EHR】"]
            for row in rows:
                lines.append(
                    f"--- id={row['id']} ---\n"
                    f"到院日期：{row['visit_date']}\n"
                    f"记录日期：{row['record_date']}\n"
                    f"诊断：{row['diagnosis']}\n"
                    f"主诉：{row['chief_complaint'] or '（无）'}\n"
                    f"检查结果：{row['exam_results'] or '（无）'}\n"
                    f"医生处置：{row['treatment'] or '（无）'}\n"
                    f"备注：{row['notes'] or '（无）'}"
                )
            parts.append("\n".join(lines))

    if target in ("interval", "all"):
        rows = db.list_interval_records(username)
        if recent_n is not None and rows:
            rows = rows[-recent_n:]
        if not rows:
            parts.append("【症状记录 Interval】\n（暂无症状记录。）")
        else:
            lines = ["【症状记录 Interval】"]
            for row in rows:
                lines.append(
                    f"--- id={row['id']} ---\n"
                    f"日期：{row['symptom_date']}\n"
                    f"记录日期：{row['record_date']}\n"
                    f"症状：{row['symptoms']}"
                )
            parts.append("\n".join(lines))

    if not parts:
        return f"（未知的读取目标：{target}，请使用 profile / ehr / interval / all。）"
    return "\n\n".join(parts)
