"""从文本里识别药品名称。"""

from __future__ import annotations

import json
import sqlite3
from functools import lru_cache

from backend.config import DATA_DIR, DRUG_CLASSI_DB_PATH


@lru_cache(maxsize=1)
def _load_drug_names() -> tuple[str, ...]:
    names: set[str] = set()

    if DRUG_CLASSI_DB_PATH.exists():
        conn = sqlite3.connect(DRUG_CLASSI_DB_PATH)
        try:
            for zh, en, aliases_json in conn.execute(
                "SELECT name_zh, name_en, aliases_zh FROM drugs_unique"
            ):
                for value in (zh, en):
                    if value and len(value.strip()) >= 2:
                        names.add(value.strip())
                try:
                    aliases = json.loads(aliases_json or "[]")
                except json.JSONDecodeError:
                    aliases = []
                for alias in aliases:
                    if alias and len(str(alias).strip()) >= 2:
                        names.add(str(alias).strip())
        finally:
            conn.close()

    interactions_db = DATA_DIR / "drug_interactions.db"
    if interactions_db.exists():
        conn = sqlite3.connect(interactions_db)
        try:
            for (drug_name,) in conn.execute("SELECT drug_name FROM drug_interactions"):
                if drug_name and len(drug_name.strip()) >= 2:
                    names.add(drug_name.strip())
        finally:
            conn.close()

    common = ("布洛芬", "对乙酰氨基酚", "阿司匹林", "二甲双胍", "头孢呋辛", "阿莫西林")
    names.update(common)

    return tuple(sorted(names, key=len, reverse=True))


@lru_cache(maxsize=1)
def _build_automaton():
    try:
        import ahocorasick
    except ImportError:
        print("[drug_tagger] pyahocorasick 未安装，药物识别已跳过")
        return None

    try:
        automaton = ahocorasick.Automaton()
        for name in _load_drug_names():
            automaton.add_word(name.lower(), name)
        automaton.make_automaton()
        return automaton
    except Exception as error:
        print(f"[drug_tagger] AC 自动机构建失败：{error}")
        return None


def _dedupe_longest_matches(matches: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    if not matches:
        return []

    sorted_matches = sorted(matches, key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str]] = []
    for start, end, name in sorted_matches:
        if any(other_start <= start and other_end >= end and (other_start, other_end) != (start, end)
               for other_start, other_end, _ in kept):
            continue
        kept.append((start, end, name))
    return sorted(kept, key=lambda item: item[0])


def find_drugs(text: str) -> list[str]:
    if not text:
        return []

    automaton = _build_automaton()
    if automaton is None:
        return []

    try:
        raw_matches: list[tuple[int, int, str]] = []
        lower_text = text.lower()
        for end_index, canonical_name in automaton.iter(lower_text):
            start_index = end_index - len(canonical_name) + 1
            raw_matches.append((start_index, end_index + 1, canonical_name))

        deduped = _dedupe_longest_matches(raw_matches)

        seen: set[str] = set()
        result: list[str] = []
        for _, _, name in deduped:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(name)
        return result
    except Exception as error:
        print(f"[drug_tagger] 药物识别失败：{error}")
        return []
