from src.config import load_settings


def test_load_settings_admin_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("LMDB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("ADMIN_IDS", "1, 2,3")

    settings = load_settings()

    assert settings.admin_ids == (1, 2, 3)


def test_load_settings_audit_chat_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("LMDB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("AUDIT_CHAT_ID", "-1001234567890, -1009876543210")

    settings = load_settings()

    assert settings.audit_chat_ids == (-1001234567890, -1009876543210)
