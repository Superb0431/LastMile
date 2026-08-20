"""分析药物相互作用。"""

import sqlite3
from itertools import combinations

from backend.config import DATA_DIR

_DB_PATH = DATA_DIR / "drug_interactions.db"


def _load_interactions(names: list[str]) -> dict[str, set[str]]:
    if not names:
        return {}

    placeholders = ",".join("?" * len(names))
    conn = sqlite3.connect(_DB_PATH)
    try:
        rows = conn.execute(
            f"""
            SELECT drug_name, interactions
            FROM drug_interactions
            WHERE lower(drug_name) IN ({placeholders})
            """,
            [n.lower() for n in names],
        ).fetchall()
    finally:
        conn.close()

    result: dict[str, set[str]] = {}
    for drug_name, interactions in rows:
        result[drug_name.lower()] = {
            x.strip().lower() for x in (interactions or "").split("|") if x.strip()
        }
    return result


def run_drug_interaction(drugs: list[str]) -> str:
    names = [d.strip() for d in drugs if d and d.strip()]
    if len(names) < 2:
        return "（请至少提供两种药物才能检查联用风险。）"

    if not _DB_PATH.exists():
        return (
            "（联用风险库不存在，请先运行以下命令："
            "python -m backend.data.build_drug_interactions）"
        )

    inter_map = _load_interactions(names)
    known_keys = set(inter_map.keys())
    unknown = [n for n in names if n.lower() not in known_keys]

    risky: list[str] = []
    safe: list[str] = []

    for a, b in combinations(names, 2):
        a_key, b_key = a.lower(), b.lower()
        pair_label = f"{a} + {b}"
        if b_key in inter_map.get(a_key, set()):
            risky.append(pair_label)
        else:
            safe.append(pair_label)

    lines = ["【药物联用风险检查结果】"]

    if risky:
        lines.append("存在高危联用风险：")
        for pair in risky:
            lines.append(f"  - {pair}")
    else:
        lines.append("在已收录范围内，未发现输入药物之间的高危联用风险。")

    if safe:
        lines.append("未发现联用风险：")
        for pair in safe:
            lines.append(f"  - {pair}")

    if unknown:
        lines.append("以下药物不在联用风险库中，无法判断：")
        for name in unknown:
            lines.append(f"  - {name}")

    lines.append("（数据来源 DDInter2.0，仅供参考，请搜索Web二次核对信息。）")
    return "\n".join(lines)
