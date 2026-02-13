from __future__ import annotations

import codecs
import io
from dataclasses import dataclass
from pathlib import Path

from .storage import HashStore


@dataclass(slots=True)
class ImportReport:
    total_lines: int
    inserted: int
    skipped_empty: int
    inserted_lines: list[str]



def import_text_blob(store: HashStore, text: str, batch_size: int) -> ImportReport:
    stream = io.StringIO(text)
    return _import_stream(store, stream, batch_size=batch_size)



def import_txt_file(store: HashStore, path: Path, batch_size: int) -> ImportReport:
    encoding = _detect_file_encoding(path)
    with path.open("r", encoding=encoding, errors="ignore", newline="") as stream:
        return _import_stream(store, stream, batch_size=batch_size)


def _detect_file_encoding(path: Path) -> str:
    sample = path.read_bytes()[:4096]

    if sample.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"

    # Prefer UTF-8 for plain ASCII/UTF-8 datasets; fallback to CP1251 for legacy exports.
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1251"



def _import_stream(store: HashStore, stream: io.TextIOBase, batch_size: int) -> ImportReport:
    total_lines = 0
    inserted = 0
    skipped_empty = 0
    batch: list[str] = []
    inserted_lines: list[str] = []

    for line in stream:
        total_lines += 1
        batch.append(line)

        if len(batch) >= batch_size:
            result = store.insert_many(batch)
            inserted += result.inserted
            skipped_empty += result.skipped_empty
            inserted_lines.extend(result.inserted_lines)
            batch.clear()

    if batch:
        result = store.insert_many(batch)
        inserted += result.inserted
        skipped_empty += result.skipped_empty
        inserted_lines.extend(result.inserted_lines)

    return ImportReport(
        total_lines=total_lines,
        inserted=inserted,
        skipped_empty=skipped_empty,
        inserted_lines=inserted_lines,
    )
