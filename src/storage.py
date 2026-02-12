from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def normalize_line(raw: str) -> str:
    compact = " ".join(raw.strip().split())
    if not compact:
        return ""

    # Accept messy combos like "email | password", "email;password" and
    # snippets where the pair is surrounded by additional junk.
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


class HashStore:
    def __init__(self, path: Path, map_size_bytes: int | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA cache_size=-400000")
        self._conn.execute("CREATE TABLE IF NOT EXISTS hashes (key BLOB PRIMARY KEY)")
        self._conn.commit()

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
