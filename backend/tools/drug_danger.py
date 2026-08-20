"""检查药品是否属于高危或特殊管理目录。"""

from __future__ import annotations

import json
import sqlite3

from backend.config import DRUG_CLASSI_DB_PATH


def run_check_drug_danger(drug_name: str) -> str:
    name = (drug_name or "").strip()
    if not name:
        return "（请提供要查询的药物名称。）"

    if not DRUG_CLASSI_DB_PATH.exists():
        return (
            "（高危药品库不存在，请先运行："
            "python backend/data/drug_classi_db/build_drug_classi_db.py）"
        )

    like = f"%{name.lower()}%"
    conn = sqlite3.connect(DRUG_CLASSI_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT name_zh, name_en, categories, sources
            FROM drugs_unique
            WHERE lower(name_zh) LIKE ?
               OR lower(name_en) LIKE ?
               OR lower(aliases_zh) LIKE ?
            """,
            (like, like, like),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return f"药物「{name}」未在高危警示药品目录中，可正常推荐。"

    hits = []
    for row in rows:
        try:
            categories = json.loads(row["categories"] or "[]")
        except json.JSONDecodeError:
            categories = [row["categories"]]
        try:
            sources = json.loads(row["sources"] or "[]")
        except json.JSONDecodeError:
            sources = [row["sources"]]
        hits.append(
            {
                "name_zh": row["name_zh"],
                "name_en": row["name_en"],
                "categories": categories,
                "sources": sources,
            }
        )

    return json.dumps(
        {
            "status": "danger",
            "message": f"药物「{name}」属于特殊管理或高警示药品，禁止直接推荐，需医生处方。",
            "matches": hits,
        },
        ensure_ascii=False,
        indent=2,
    )
