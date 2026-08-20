"""构建药物相互作用数据。"""

import sqlite3
from pathlib import Path

SRC = Path(__file__).with_name("drug_safety.db")
DST = Path(__file__).with_name("drug_interactions.db")


def build() -> int:
    if not SRC.exists():
        raise FileNotFoundError(f"源库不存在：{SRC}")

    src = sqlite3.connect(SRC)
    try:
        rows = src.execute(
            "SELECT drug_name, high_risk_drug_interactions FROM drug_safety"
        ).fetchall()
    finally:
        src.close()

    display: dict[str, str] = {}
    adj: dict[str, set[str]] = {}

    def canon(name: str) -> str:
        key = name.strip().lower()
        display.setdefault(key, name.strip())
        return key

    for name, inter in rows:
        a = canon(name)
        adj.setdefault(a, set())
        for raw in (inter or "").split("|"):
            if not raw.strip():
                continue
            b = canon(raw)
            adj[a].add(b)
            adj.setdefault(b, set()).add(a)

    dst = sqlite3.connect(DST)
    try:
        dst.execute("DROP TABLE IF EXISTS drug_interactions")
        dst.execute(
            """
            CREATE TABLE drug_interactions (
                drug_name    TEXT PRIMARY KEY,
                interactions TEXT
            )
            """
        )
        for key, neighbors in adj.items():
            names = sorted(display[n] for n in neighbors)
            dst.execute(
                "INSERT INTO drug_interactions VALUES (?, ?)",
                (display[key], "|".join(names)),
            )
        dst.commit()
        count = dst.execute("SELECT COUNT(*) FROM drug_interactions").fetchone()[0]
    finally:
        dst.close()

    return count


if __name__ == "__main__":
    n = build()
    print(f"已生成 {DST}，共 {n} 行。")
