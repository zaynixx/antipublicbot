from src.bot import _admin_keyboard, _admin_panel_keyboard, _extract_unique_lines_payload, _main_keyboard, _render_user_link


def test_admin_keyboard_contains_only_admin_entrypoint():
    keyboard = _admin_keyboard().keyboard
    flat = [button.text for row in keyboard for button in row]

    assert "🛠 Админка" in flat
    assert "💳 Выдать баланс" not in flat
    assert "🧾 Отчет по пользователю" not in flat
    assert "👥 Список пользователей" not in flat
    assert "📦 Выгрузка пользователя" not in flat


def test_admin_panel_inline_keyboard_contains_all_admin_actions():
    inline_keyboard = _admin_panel_keyboard().inline_keyboard
    flat = [button.text for row in inline_keyboard for button in row]

    assert "💳 Выдать баланс" in flat
    assert "🧾 Отчет по пользователю" in flat
    assert "👥 Список пользователей" in flat
    assert "📦 Выгрузка пользователя" in flat


def test_user_keyboard_hides_download_actions():
    keyboard = _main_keyboard().keyboard
    flat = [button.text for row in keyboard for button in row]

    assert "📥 Скачать файл" not in flat


def test_render_user_link_prefers_username_or_fallbacks_to_tg_profile():
    assert _render_user_link(123, "telegram_user") == '<a href="https://t.me/telegram_user">@telegram_user</a>'
    assert _render_user_link(321, "") == '<a href="tg://user?id=321">профиль</a>'


def test_extract_unique_lines_payload_deduplicates_and_trims(tmp_path):
    source = tmp_path / "upload.txt"
    source.write_text(" user@example.com ; pass1\nuser@example.com:pass1\n USER@example.com\tpass1 \n two \n", encoding="utf-8")

    payload = _extract_unique_lines_payload(source)

    assert payload == "user@example.com:pass1\ntwo".encode("utf-8")


def test_extract_unique_lines_payload_returns_none_for_only_empty_lines(tmp_path):
    source = tmp_path / "upload.txt"
    source.write_text("\n \n\t\n", encoding="utf-8")

    payload = _extract_unique_lines_payload(source)

    assert payload is None
