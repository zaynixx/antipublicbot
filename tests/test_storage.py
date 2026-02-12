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


def test_balance_upload_history_and_checks(tmp_path: Path):
    db = HashStore(tmp_path / "test.sqlite3")
    try:
        assert db.get_balance(100) == 0
        assert db.add_balance(100, 15) == 15
        assert db.add_balance(100, 5) == 20
        assert db.spend_balance(100, 7) is True
        assert db.get_balance(100) == 13
        assert db.spend_balance(100, 100) is False
        assert db.get_balance(100) == 13

        db.record_upload(100, "a.txt", inserted=3, total_lines=4, stored_path="/tmp/a.txt")
        db.record_upload(100, "b.txt", inserted=7, total_lines=9, stored_path="/tmp/b.txt")

        db.record_check(100, "first@example.com:pass", found=True)
        db.record_check(100, "first@example.com:pass", found=False)
        db.record_check(100, "second@example.com:pass", found=False)

        history = db.get_recent_uploads(100)
        assert len(history) == 2
        assert history[0].id > history[1].id
        assert history[0].filename == "b.txt"
        assert history[0].inserted == 7
        assert history[0].stored_path == "/tmp/b.txt"
        assert history[1].filename == "a.txt"

        picked = db.get_upload(100, history[1].id)
        assert picked is not None
        assert picked.filename == "a.txt"

        recent_checks = db.get_recent_checks(100)
        assert len(recent_checks) == 3
        assert recent_checks[0].query == "second@example.com:pass"

        unique_checks = db.get_unique_checked_queries(100)
        assert unique_checks == ["second@example.com:pass", "first@example.com:pass"]

        stats = db.get_user_stats(100)
        assert stats["balance"] == 13
        assert stats["uploads_count"] == 2
        assert stats["uploads_total_lines"] == 13
        assert stats["uploads_total_inserted"] == 10
        assert stats["checks_count"] == 3
        assert stats["checks_found"] == 1
        assert stats["checks_not_found"] == 2
        assert stats["unique_checks_count"] == 2

        db.add_balance(200, 1)
        users = db.list_known_user_ids()
        assert users[0] in {100, 200}
        assert sorted(users) == [100, 200]
    finally:
        db.close()
