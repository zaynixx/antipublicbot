from src.bot import _admin_keyboard, _admin_panel_keyboard, _build_unique_lines_payload, _main_keyboard, _render_user_link


def test_admin_keyboard_contains_only_admin_entrypoint():
    keyboard = _admin_keyboard().keyboard
    flat = [button.text for row in keyboard for button in row]

    assert "🛠 Админка" in flat
    assert "💳 Выдать баланс" not in flat
    assert "🧾 Отчет по пользователю" not in flat
    assert "👥 Список пользователей" not in flat
    assert "📦 Выгрузка пользователя" not in flat
    assert "💬 Комментарий к файлу" not in flat


def test_admin_panel_inline_keyboard_contains_all_admin_actions():
    inline_keyboard = _admin_panel_keyboard().inline_keyboard
    flat = [button.text for row in inline_keyboard for button in row]

    assert "💳 Выдать баланс" in flat
    assert "🧾 Отчет по пользователю" in flat
    assert "👥 Список пользователей" in flat
    assert "📦 Выгрузка пользователя" in flat
    assert "💬 Комментарий к файлу" in flat


def test_user_keyboard_hides_download_actions():
    keyboard = _main_keyboard().keyboard
    flat = [button.text for row in keyboard for button in row]

    assert "📥 Скачать файл" not in flat


def test_render_user_link_prefers_username_or_fallbacks_to_tg_profile():
    assert _render_user_link(123, "telegram_user") == '<a href="https://t.me/telegram_user">@telegram_user</a>'
    assert _render_user_link(321, "") == '<a href="tg://user?id=321">профиль</a>'


def test_build_unique_lines_payload_joins_lines():
    payload = _build_unique_lines_payload(["user@example.com:pass1", "two"])

    assert payload == "user@example.com:pass1\ntwo".encode("utf-8")


def test_build_unique_lines_payload_returns_none_for_empty_input():
    payload = _build_unique_lines_payload([])

    assert payload is None
