from pathlib import Path

from src.importers import import_text_blob, import_txt_file
from src.storage import HashStore


def test_import_text_blob(tmp_path: Path):
    db = HashStore(tmp_path / "blob.lmdb", map_size_bytes=64 * 1024 * 1024)
    try:
        report = import_text_blob(db, "a\n\n b \na\n", batch_size=2)
        assert report.total_lines == 4
        assert report.inserted == 2
        assert report.skipped_empty == 1
    finally:
        db.close()


def test_import_txt_file(tmp_path: Path):
    p = tmp_path / "in.txt"
    p.write_text("x\ny\n", encoding="utf-8")
    db = HashStore(tmp_path / "file.lmdb", map_size_bytes=64 * 1024 * 1024)
    try:
        report = import_txt_file(db, p, batch_size=100)
        assert report.total_lines == 2
        assert report.inserted == 2
    finally:
        db.close()


def test_import_utf16_txt_file(tmp_path: Path):
    p = tmp_path / "utf16.txt"
    p.write_text("user@example.com:pass\n", encoding="utf-16")
    db = HashStore(tmp_path / "utf16.lmdb", map_size_bytes=64 * 1024 * 1024)
    try:
        report = import_txt_file(db, p, batch_size=100)
        assert report.total_lines == 1
        assert report.inserted == 1
        assert db.contains("user@example.com:pass") is True
    finally:
        db.close()
