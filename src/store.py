"""초안과 '이미 다룬 책' 기록을 담는 작은 데이터베이스(SQLite)."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .settings import DB_PATH, OUT_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn13        TEXT NOT NULL,
    title         TEXT NOT NULL,
    author        TEXT,
    publisher     TEXT,
    pub_date      TEXT,
    cover_url     TEXT,
    link          TEXT,
    category      TEXT,
    source_desc   TEXT,
    toc           TEXT,
    threads_text  TEXT,
    slides_json   TEXT,
    search_line   TEXT,
    hashtags      TEXT,
    card_paths    TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',
    note          TEXT,
    threads_id    TEXT,
    instagram_id  TEXT,
    created_at    TEXT NOT NULL,
    published_at  TEXT
);

CREATE TABLE IF NOT EXISTS seen (
    isbn13   TEXT PRIMARY KEY,
    title    TEXT,
    seen_at  TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@contextmanager
def conn():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        _migrate(c)
        yield c
        c.commit()
    finally:
        c.close()


def _migrate(c: sqlite3.Connection) -> None:
    """예전 버전으로 만든 DB에 새 칸을 붙입니다."""
    existing = {row["name"] for row in c.execute("PRAGMA table_info(drafts)")}
    for column, ddl in (("search_line", "TEXT"),):
        if column not in existing:
            c.execute(f"ALTER TABLE drafts ADD COLUMN {column} {ddl}")


def already_seen(isbn13: str) -> bool:
    with conn() as c:
        row = c.execute("SELECT 1 FROM seen WHERE isbn13 = ?", (isbn13,)).fetchone()
        return row is not None


def mark_seen(isbn13: str, title: str) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO seen (isbn13, title, seen_at) VALUES (?, ?, ?)",
            (isbn13, title, now()),
        )


def save_draft(book: dict, copy: dict, card_paths: list[str]) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO drafts
               (isbn13, title, author, publisher, pub_date, cover_url, link, category,
                source_desc, toc, threads_text, slides_json, search_line, hashtags,
                card_paths, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?)""",
            (
                book["isbn13"],
                book["title"],
                book.get("author"),
                book.get("publisher"),
                book.get("pub_date"),
                book.get("cover_url"),
                book.get("link"),
                book.get("category"),
                book.get("description"),
                book.get("toc"),
                copy["threads_text"],
                json.dumps(copy["slides"], ensure_ascii=False),
                copy.get("search_line", ""),
                " ".join(copy["hashtags"]),
                json.dumps(card_paths, ensure_ascii=False),
                now(),
            ),
        )
        return int(cur.lastrowid)


def list_drafts(status: str | None = "draft") -> list[dict]:
    with conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM drafts WHERE status = ? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT 100").fetchall()
        return [_row_to_dict(r) for r in rows]


def get_draft(draft_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        return _row_to_dict(row) if row else None


def update_text(draft_id: int, threads_text: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE drafts SET threads_text = ? WHERE id = ?", (threads_text, draft_id)
        )


def update_search_line(draft_id: int, search_line: str) -> None:
    with conn() as c:
        c.execute(
            "UPDATE drafts SET search_line = ? WHERE id = ?", (search_line, draft_id)
        )


def mark_published(draft_id: int, threads_id: str | None, instagram_id: str | None) -> None:
    with conn() as c:
        c.execute(
            """UPDATE drafts SET status='published', threads_id=?, instagram_id=?,
               published_at=? WHERE id=?""",
            (threads_id, instagram_id, now(), draft_id),
        )


def mark_failed(draft_id: int, note: str) -> None:
    with conn() as c:
        c.execute("UPDATE drafts SET status='failed', note=? WHERE id=?", (note, draft_id))


def mark_skipped(draft_id: int) -> None:
    with conn() as c:
        c.execute("UPDATE drafts SET status='skipped' WHERE id=?", (draft_id,))


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["slides"] = json.loads(d.get("slides_json") or "[]")
    d["cards"] = json.loads(d.get("card_paths") or "[]")
    d["alts"] = [s.get("alt", "") for s in d["slides"]]
    return d
