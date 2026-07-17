"""build_docs_index."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import DOCS_INDEX_DB_PATH, MEDICAL_DOCS_DIR

SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)

def _parse_markdown(path: Path) -> tuple[str, str, list[tuple[str, str]]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = path.stem
    doc_id = path.stem
    source = "local"
    for line in lines[:10]:
        if line.startswith("# "):
            title = line[2:].strip()
        if line.startswith("doc_id:"):
            doc_id = line.split(":", 1)[1].strip()
        if line.startswith("source:"):
            source = line.split(":", 1)[1].strip()

    sections: list[tuple[str, str]] = []
    current_section = "概述"
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current_lines:
                sections.append((current_section, "\n".join(current_lines).strip()))
            current_section = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_section, "\n".join(current_lines).strip()))
    return doc_id, title, sections if sections else [(title, text)]

def build_index() -> None:
    MEDICAL_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_INDEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DOCS_INDEX_DB_PATH.exists():
        DOCS_INDEX_DB_PATH.unlink()

    conn = sqlite3.connect(DOCS_INDEX_DB_PATH)
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE docs_fts USING fts5(
                doc_id UNINDEXED,
                title,
                section,
                content,
                source UNINDEXED
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE docs_meta (
                doc_id TEXT PRIMARY KEY,
                title TEXT,
                source TEXT,
                year INTEGER,
                file_path TEXT
            )
            """
        )

        for md_path in sorted(MEDICAL_DOCS_DIR.glob("*.md")):
            doc_id, title, sections = _parse_markdown(md_path)
            year = 2024
            for line in md_path.read_text(encoding="utf-8").splitlines()[:10]:
                if line.startswith("year:"):
                    try:
                        year = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        year = 2024
            conn.execute(
                "INSERT INTO docs_meta (doc_id, title, source, year, file_path) VALUES (?, ?, ?, ?, ?)",
                (doc_id, title, "local", year, str(md_path)),
            )
            for section, content in sections:
                if not content.strip():
                    continue
                conn.execute(
                    "INSERT INTO docs_fts (doc_id, title, section, content, source) VALUES (?, ?, ?, ?, ?)",
                    (doc_id, title, section, content, "local"),
                )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM docs_fts").fetchone()[0]
        print(f"索引完成：{count} 个片段 -> {DOCS_INDEX_DB_PATH}")
    finally:
        conn.close()

if __name__ == "__main__":
    build_index()
