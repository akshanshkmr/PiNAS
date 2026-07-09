"""SQLite tag cache: caption + tags per file, keyed by path + mtime.

Kept intentionally simple — a single table, JSON-encoded tags, LIKE-based
search. The volume is per-photo not per-word, so this scales to tens of
thousands of NAS files without needing FTS.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "tags.db"
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tag (
              path       TEXT PRIMARY KEY,
              mtime      REAL NOT NULL,
              caption    TEXT NOT NULL DEFAULT '',
              tags       TEXT NOT NULL DEFAULT '[]',
              updated_at INTEGER NOT NULL
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS tag_caption ON tag(caption)")


def get(path: str, mtime: float | None = None) -> dict | None:
    """Return {caption, tags, mtime, updated_at} if a fresh entry exists.

    If `mtime` is provided, entries with a different mtime are treated as
    stale and returned as None (so a re-tag will overwrite them).
    """
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM tag WHERE path = ?", (path,)).fetchone()
    if not row:
        return None
    if mtime is not None and abs(row["mtime"] - mtime) > 0.5:
        return None
    return {
        "caption": row["caption"],
        "tags": json.loads(row["tags"] or "[]"),
        "mtime": row["mtime"],
        "updated_at": row["updated_at"],
    }


def put(path: str, mtime: float, caption: str, tags: list[str]) -> None:
    with _lock, _conn() as c:
        c.execute(
            """
            INSERT INTO tag (path, mtime, caption, tags, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              mtime = excluded.mtime,
              caption = excluded.caption,
              tags = excluded.tags,
              updated_at = excluded.updated_at
            """,
            (path, mtime, caption, json.dumps(tags), int(time.time())),
        )


def delete(path: str) -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM tag WHERE path = ? OR path LIKE ?", (path, path.rstrip("/") + "/%"))


def entries_for_paths(paths: list[str]) -> dict[str, dict]:
    """Bulk fetch for a folder listing. Returns {path: {caption, tags, mtime}}."""
    if not paths:
        return {}
    with _lock, _conn() as c:
        placeholders = ",".join("?" * len(paths))
        rows = c.execute(
            f"SELECT path, mtime, caption, tags FROM tag WHERE path IN ({placeholders})",
            paths,
        ).fetchall()
    return {
        r["path"]: {"caption": r["caption"], "tags": json.loads(r["tags"] or "[]"), "mtime": r["mtime"]}
        for r in rows
    }


def search(query: str, root: str | None = None, limit: int = 200) -> list[dict]:
    """Substring search across captions and tags. Returns [{path, caption, tags, mtime}]."""
    q = f"%{query.strip().lower()}%"
    sql = "SELECT path, mtime, caption, tags FROM tag WHERE (LOWER(caption) LIKE ? OR LOWER(tags) LIKE ?)"
    params: list = [q, q]
    if root:
        sql += " AND path LIKE ?"
        params.append(root.rstrip("/") + "/%")
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with _lock, _conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [
        {
            "path": r["path"],
            "name": os.path.basename(r["path"]),
            "caption": r["caption"],
            "tags": json.loads(r["tags"] or "[]"),
            "mtime": r["mtime"],
        }
        for r in rows
    ]


def stats() -> dict:
    with _lock, _conn() as c:
        row = c.execute("SELECT COUNT(*) AS n, MAX(updated_at) AS latest FROM tag").fetchone()
    return {"count": row["n"], "latest": row["latest"] or 0}
