"""Public share links for the Files tab.

Every share is a random 24-byte URL-safe token stored in SQLite. Access is
scoped to exactly the shared path (and its children if it's a folder).
Expiry, revocation, hit counts, and an optional password are enforced
server-side.

Nothing here trusts the URL — every request re-runs `files.resolve` to make
sure the requested asset is still inside the sandboxed NAS roots.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import files

_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "shares.db"
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
            CREATE TABLE IF NOT EXISTS share (
              token         TEXT PRIMARY KEY,
              path          TEXT NOT NULL,
              is_dir        INTEGER NOT NULL,
              mode          TEXT NOT NULL DEFAULT 'view',   -- 'view' or 'download'
              password_hash TEXT,                            -- optional; sha256(salt+password)
              password_salt TEXT,
              public        INTEGER NOT NULL DEFAULT 0,      -- 1 = Funnel-exposed
              created_at    INTEGER NOT NULL,
              expires_at    INTEGER,                         -- NULL = never expires
              hits          INTEGER NOT NULL DEFAULT 0,
              last_seen_at  INTEGER,
              created_by    TEXT NOT NULL,
              label         TEXT
            )
            """
        )


@dataclass
class Share:
    token: str
    path: str
    is_dir: bool
    mode: str
    public: bool
    created_at: int
    expires_at: int | None
    hits: int
    last_seen_at: int | None
    created_by: str
    label: str | None
    has_password: bool


def _row_to_share(row) -> Share:
    return Share(
        token=row["token"],
        path=row["path"],
        is_dir=bool(row["is_dir"]),
        mode=row["mode"],
        public=bool(row["public"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        hits=row["hits"],
        last_seen_at=row["last_seen_at"],
        created_by=row["created_by"],
        label=row["label"],
        has_password=bool(row["password_hash"]),
    )


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def create(
    path: str,
    ttl_seconds: int | None,
    mode: str,
    public: bool,
    created_by: str,
    password: str | None = None,
    label: str | None = None,
) -> Share:
    # sandbox check + kind detection
    target = files.resolve(path)
    is_dir = target.is_dir()
    if not is_dir and not target.is_file():
        raise FileNotFoundError("Not found.")
    if mode not in ("view", "download"):
        raise ValueError("Unknown share mode.")

    token = secrets.token_urlsafe(24)
    now = int(time.time())
    expires_at = now + ttl_seconds if ttl_seconds and ttl_seconds > 0 else None
    salt = secrets.token_hex(8) if password else None
    pw_hash = _hash_password(password, salt) if password else None

    with _lock, _conn() as c:
        c.execute(
            """
            INSERT INTO share (token, path, is_dir, mode, password_hash, password_salt,
                               public, created_at, expires_at, created_by, label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (token, str(target), 1 if is_dir else 0, mode, pw_hash, salt,
             1 if public else 0, now, expires_at, created_by, label),
        )
        row = c.execute("SELECT * FROM share WHERE token = ?", (token,)).fetchone()
    return _row_to_share(row)


def list_all(created_by: str | None = None) -> list[Share]:
    with _lock, _conn() as c:
        if created_by:
            rows = c.execute(
                "SELECT * FROM share WHERE created_by = ? ORDER BY created_at DESC", (created_by,)
            ).fetchall()
        else:
            rows = c.execute("SELECT * FROM share ORDER BY created_at DESC").fetchall()
    return [_row_to_share(r) for r in rows]


def get(token: str) -> Share | None:
    if not token or len(token) < 8:
        return None
    with _lock, _conn() as c:
        row = c.execute("SELECT * FROM share WHERE token = ?", (token,)).fetchone()
    return _row_to_share(row) if row else None


def delete(token: str) -> bool:
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM share WHERE token = ?", (token,))
        return cur.rowcount > 0


def bump_hit(token: str) -> None:
    with _lock, _conn() as c:
        c.execute(
            "UPDATE share SET hits = hits + 1, last_seen_at = ? WHERE token = ?",
            (int(time.time()), token),
        )


def check_password(share: Share, password: str) -> bool:
    if not share.has_password:
        return True
    with _lock, _conn() as c:
        row = c.execute(
            "SELECT password_hash, password_salt FROM share WHERE token = ?", (share.token,)
        ).fetchone()
    if not row or not row["password_hash"] or not row["password_salt"]:
        return False
    supplied = _hash_password(password, row["password_salt"])
    return hmac.compare_digest(supplied, row["password_hash"])


def is_expired(share: Share) -> bool:
    return share.expires_at is not None and share.expires_at <= int(time.time())


def scope_check(share: Share, requested_path: str) -> Path:
    """Verify that `requested_path` is either the shared path itself or a
    child of it (if the share is a folder). Raises PermissionError."""
    # first: normal NAS sandbox — refuses .. / symlink escapes
    target = files.resolve(requested_path)
    scope = Path(share.path).resolve()
    try:
        if target == scope:
            return target
        target.relative_to(scope)
    except ValueError:
        raise PermissionError("Path is outside the share scope.")
    if not share.is_dir and target != scope:
        raise PermissionError("Path is outside the share scope.")
    return target


def purge_expired() -> int:
    """Drop expired shares; return how many were removed."""
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM share WHERE expires_at IS NOT NULL AND expires_at <= ?",
                        (int(time.time()),))
        return cur.rowcount
