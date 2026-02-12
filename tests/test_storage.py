from pathlib import Path

from src.storage import HashStore, line_key, normalize_line


def test_normalize_line():
    assert normalize_line("  a   b	 c  ") == "a b c"


def test_normalize_line_extracts_login_password_pair():
    assert normalize_line("ma937641@wipro.com:Pestejud123.") == "ma937641@wipro.com:Pestejud123."
    assert normalize_line("  ma937641@wipro.com | Pestejud123.  ") == "ma937641@wipro.com:Pestejud123."
    assert (
        normalize_line("text before 09000739@stccebu.online ; 07282010!Ae extra")
        == "09000739@stccebu.online:07282010!Ae"
    )


def test_line_key_empty():
    assert line_key("   ") == b""


def test_insert_and_contains(tmp_path: Path):
    db = HashStore(tmp_path / "test.lmdb", map_size_bytes=64 * 1024 * 1024)
    try:
        assert db.insert_one("test@example.com") is True
        assert db.insert_one("test@example.com") is False
        assert db.contains("test@example.com") is True
        assert db.contains("missing@example.com") is False
    finally:
        db.close()


def test_balance_and_upload_history(tmp_path: Path):
    db = HashStore(tmp_path / "test.sqlite3")
    try:
        assert db.get_balance(100) == 0
        assert db.add_balance(100, 15) == 15
        assert db.add_balance(100, 5) == 20

        db.record_upload(100, "a.txt", inserted=3, total_lines=4)
        db.record_upload(100, "b.txt", inserted=7, total_lines=9)

        history = db.get_recent_uploads(100)
        assert len(history) == 2
        assert history[0].filename == "b.txt"
        assert history[0].inserted == 7
        assert history[1].filename == "a.txt"
    finally:
        db.close()
