from src.bot import _admin_keyboard


def test_admin_keyboard_contains_all_admin_actions():
    keyboard = _admin_keyboard().keyboard
    flat = [button.text for row in keyboard for button in row]

    assert "🛠 Админка" in flat
    assert "💳 Выдать баланс" in flat
    assert "🧾 Отчет по пользователю" in flat
    assert "👥 Список пользователей" in flat
