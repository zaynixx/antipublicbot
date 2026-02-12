from pathlib import Path

from src.storage import HashStore, line_key, normalize_line


def test_normalize_line():
    assert normalize_line("  a   b\t c  ") == "a b c"


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
