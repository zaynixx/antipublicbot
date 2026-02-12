from __future__ import annotations

import argparse
import time
from pathlib import Path

from .importers import import_txt_file
from .storage import HashStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.bootstrap",
        description="Импортирует большие .txt базы в локальное хранилище anti-public бота.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="Один или несколько .txt файлов для импорта.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path("./data/antipublic.sqlite3"),
        help="Путь к SQLite базе (по умолчанию: ./data/antipublic.sqlite3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Размер батча на запись (по умолчанию: 5000)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    for path in args.files:
        if not path.exists():
            parser.error(f"Файл не найден: {path}")
        if path.suffix.lower() != ".txt":
            parser.error(f"Поддерживаются только .txt файлы: {path}")

    db = HashStore(args.db_path)
    try:
        overall_lines = 0
        overall_inserted = 0
        overall_empty = 0

        for file_path in args.files:
            started = time.perf_counter()
            report = import_txt_file(db, file_path, batch_size=args.batch_size)
            elapsed = time.perf_counter() - started

            overall_lines += report.total_lines
            overall_inserted += report.inserted
            overall_empty += report.skipped_empty

            print(
                f"[OK] {file_path} | lines={report.total_lines} inserted={report.inserted} "
                f"empty={report.skipped_empty} time={elapsed:.2f}s"
            )

        stat = db.stat()
        print(
            "\nИтог: "
            f"lines={overall_lines}, inserted={overall_inserted}, empty={overall_empty}, "
            f"entries_in_db={stat['entries']}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
