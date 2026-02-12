from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def normalize_line(raw: str) -> str:
    compact = " ".join(raw.strip().split())
    if not compact:
        return ""

    match = re.search(
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\s*[:;|,\t ]\s*(\S+)",
        compact,
    )
    if match:
        login, password = match.groups()
        return f"{login.lower()}:{password}"

    return compact


def line_key(line: str) -> bytes:
    normalized = normalize_line(line)
    if not normalized:
        return b""
    return hashlib.blake2b(normalized.encode("utf-8"), digest_size=16).digest()


@dataclass(slots=True)
class InsertResult:
    inserted: int
    skipped_empty: int


@dataclass(slots=True)
class UploadRecord:
    id: int
    filename: str
    inserted: int
    total_lines: int
    created_at: str
    stored_path: str


@dataclass(slots=True)
class CheckRecord:
    id: int
    query: str
    normalized_query: str
    found: int
    created_at: str


class HashStore:
    def __init__(self, path: Path, map_size_bytes: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA cache_size=-400000")
        self._conn.execute("CREATE TABLE IF NOT EXISTS hashes (key BLOB PRIMARY KEY)")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                inserted INTEGER NOT NULL,
                total_lines INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                stored_path TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                normalized_query TEXT NOT NULL,
                found INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        if not self._has_uploads_stored_path():
            self._conn.execute("ALTER TABLE uploads ADD COLUMN stored_path TEXT")
        self._conn.commit()

    def _has_uploads_stored_path(self) -> bool:
        cols = self._conn.execute("PRAGMA table_info(uploads)").fetchall()
        return any(col[1] == "stored_path" for col in cols)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def close(self) -> None:
        self._conn.close()

    def contains(self, line: str) -> bool:
        key = line_key(line)
        if not key:
            return False
        row = self._conn.execute("SELECT 1 FROM hashes WHERE key=?", (key,)).fetchone()
        return row is not None

    def insert_one(self, line: str) -> bool:
        key = line_key(line)
        if not key:
            return False
        cur = self._conn.execute("INSERT OR IGNORE INTO hashes(key) VALUES (?)", (key,))
        self._conn.commit()
        return cur.rowcount == 1

    def insert_many(self, lines: Iterable[str]) -> InsertResult:
        inserted = 0
        skipped_empty = 0
        keys: list[tuple[bytes]] = []

        for line in lines:
            key = line_key(line)
            if not key:
                skipped_empty += 1
                continue
            keys.append((key,))

        if keys:
            before = self._conn.total_changes
            self._conn.executemany("INSERT OR IGNORE INTO hashes(key) VALUES (?)", keys)
            self._conn.commit()
            inserted = self._conn.total_changes - before

        return InsertResult(inserted=inserted, skipped_empty=skipped_empty)

    def stat(self) -> dict:
        entries = self._conn.execute("SELECT COUNT(*) FROM hashes").fetchone()[0]
        return {
            "entries": entries,
            "map_size": 0,
            "last_pgno": 0,
        }

    def get_balance(self, user_id: int) -> int:
        row = self._conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        return int(row[0]) if row else 0

    def add_balance(self, user_id: int, amount: int) -> int:
        now = self._utc_now()
        self._conn.execute(
            """
            INSERT INTO users(user_id, balance, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                balance = balance + excluded.balance,
                updated_at = excluded.updated_at
            """,
            (user_id, amount, now),
        )
        self._conn.commit()
        return self.get_balance(user_id)

    def spend_balance(self, user_id: int, amount: int) -> bool:
        if amount <= 0:
            return True

        now = self._utc_now()
        cur = self._conn.execute(
            """
            UPDATE users
            SET balance = balance - ?, updated_at = ?
            WHERE user_id = ? AND balance >= ?
            """,
            (amount, now, user_id, amount),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def record_upload(
        self,
        user_id: int,
        filename: str,
        inserted: int,
        total_lines: int,
        stored_path: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO uploads(user_id, filename, inserted, total_lines, created_at, stored_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, filename, inserted, total_lines, self._utc_now(), stored_path),
        )
        self._conn.commit()

    def record_check(self, user_id: int, query: str, found: bool) -> None:
        normalized_query = normalize_line(query)
        self._conn.execute(
            """
            INSERT INTO checks(user_id, query, normalized_query, found, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, query.strip(), normalized_query, 1 if found else 0, self._utc_now()),
        )
        self._conn.commit()

    def get_recent_uploads(self, user_id: int, limit: int = 5) -> list[UploadRecord]:
        rows = self._conn.execute(
            """
            SELECT id, filename, inserted, total_lines, created_at, COALESCE(stored_path, '')
            FROM uploads
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [UploadRecord(*row) for row in rows]

    def get_recent_checks(self, user_id: int, limit: int = 10) -> list[CheckRecord]:
        rows = self._conn.execute(
            """
            SELECT id, query, normalized_query, found, created_at
            FROM checks
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [CheckRecord(*row) for row in rows]

    def get_unique_checked_queries(self, user_id: int, limit: int = 20) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT normalized_query
            FROM checks
            WHERE user_id=? AND normalized_query != ''
            GROUP BY normalized_query
            ORDER BY MAX(id) DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def list_known_user_ids(self, limit: int = 100) -> list[int]:
        rows = self._conn.execute(
            """
            SELECT user_id
            FROM (
                SELECT user_id, MAX(created_at) AS latest_ts FROM uploads GROUP BY user_id
                UNION ALL
                SELECT user_id, MAX(created_at) AS latest_ts FROM checks GROUP BY user_id
                UNION ALL
                SELECT user_id, updated_at AS latest_ts FROM users
            )
            GROUP BY user_id
            ORDER BY MAX(latest_ts) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [int(row[0]) for row in rows]

    def get_user_stats(self, user_id: int) -> dict[str, int]:
        upload_row = self._conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(total_lines), 0), COALESCE(SUM(inserted), 0)
            FROM uploads
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()
        check_row = self._conn.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(found), 0)
            FROM checks
            WHERE user_id=?
            """,
            (user_id,),
        ).fetchone()
        unique_checks = self._conn.execute(
            """
            SELECT COUNT(DISTINCT normalized_query)
            FROM checks
            WHERE user_id=? AND normalized_query != ''
            """,
            (user_id,),
        ).fetchone()

        checks_count = int(check_row[0])
        checks_found = int(check_row[1])
        return {
            "balance": self.get_balance(user_id),
            "uploads_count": int(upload_row[0]),
            "uploads_total_lines": int(upload_row[1]),
            "uploads_total_inserted": int(upload_row[2]),
            "checks_count": checks_count,
            "checks_found": checks_found,
            "checks_not_found": checks_count - checks_found,
            "unique_checks_count": int(unique_checks[0]),
        }

    def get_upload(self, user_id: int, upload_id: int) -> UploadRecord | None:
        row = self._conn.execute(
            """
            SELECT id, filename, inserted, total_lines, created_at, COALESCE(stored_path, '')
            FROM uploads
            WHERE user_id=? AND id=?
            """,
            (user_id, upload_id),
        ).fetchone()
        return UploadRecord(*row) if row else None
