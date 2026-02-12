from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from .storage import HashStore


@dataclass(slots=True)
class ImportReport:
    total_lines: int
    inserted: int
    skipped_empty: int



def import_text_blob(store: HashStore, text: str, batch_size: int) -> ImportReport:
    stream = io.StringIO(text)
    return _import_stream(store, stream, batch_size=batch_size)



def import_txt_file(store: HashStore, path: Path, batch_size: int) -> ImportReport:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        return _import_stream(store, f, batch_size=batch_size)



def _import_stream(store: HashStore, stream: io.TextIOBase, batch_size: int) -> ImportReport:
    total_lines = 0
    inserted = 0
    skipped_empty = 0
    batch: list[str] = []

    for line in stream:
        total_lines += 1
        batch.append(line)

        if len(batch) >= batch_size:
            result = store.insert_many(batch)
            inserted += result.inserted
            skipped_empty += result.skipped_empty
            batch.clear()

    if batch:
        result = store.insert_many(batch)
        inserted += result.inserted
        skipped_empty += result.skipped_empty

    return ImportReport(
        total_lines=total_lines,
        inserted=inserted,
        skipped_empty=skipped_empty,
    )
