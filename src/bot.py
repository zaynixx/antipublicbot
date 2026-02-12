from __future__ import annotations

import tempfile
from pathlib import Path
from shutil import copy2

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings, load_settings
from .importers import import_text_blob, import_txt_file
from .storage import HashStore


async def welcome(name: str) -> str:
    return f"""🤚🏻 Добро пожаловать, {name},
Это бот по по приему строк Login.microsoftonline.com
Надеюсь мы с тобой отлично сработаемся!"""


SUPPORT = """📞 Тех поддержка - @rezer_2281
Постараемся решить вашу проблему !"""

RULES = """❗️ Правила
При использовании данного бота, вы соглашаетесь на то, что мы выполняем свою работу корректно.
В дополнении согласны с тем, что результаты после проверки — верные.
Оскорбления в адрес бота или нас — бан в боте.

Отработка строк происходит следующим образом:
1. Бот принимает ваши строки и сверяет их на уникальность в нашей базе.
2. С помощью регулярок в notepad++ удаляются не нужные строки.
3. Проверка самописным чекером с приватными прокси.

Если у вас остались вопросы — @rezer_2281"""

SEND_TEXT_FILE = """Отправьте мне Текстовый документ с аккаунтами в формате:  mail:password."""
SEND_FILE_LINK = """Пожалуйста загрузите ваши passwords.txt"""
WAIT_FOR_CHECK = """❗️ Проверяю строки на уникальность...
После этого сообщения выдам результаты."""


async def upload_processed(unique_count: int) -> str:
    return f"""Ваш файл был обработан.
Уникальных строк: {unique_count}
Спасибо что работаете с нами!
"""


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📜 Правила"), KeyboardButton("🛟 Поддержка")],
            [KeyboardButton("📂 Загрузить файл"), KeyboardButton("🔍 Проверить строку")],
            [KeyboardButton("👤 Профиль"), KeyboardButton("📥 Скачать файл")],
        ],
        resize_keyboard=True,
    )


def _admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📜 Правила"), KeyboardButton("🛟 Поддержка")],
            [KeyboardButton("📂 Загрузить файл"), KeyboardButton("🔍 Проверить строку")],
            [KeyboardButton("👤 Профиль"), KeyboardButton("📥 Скачать файл")],
            [KeyboardButton("🛠 Админка")],
        ],
        resize_keyboard=True,
    )


def _store(ctx: ContextTypes.DEFAULT_TYPE) -> HashStore:
    return ctx.application.bot_data["store"]


def _settings(ctx: ContextTypes.DEFAULT_TYPE) -> Settings:
    return ctx.application.bot_data["settings"]


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids


def _try_charge_balance(ctx: ContextTypes.DEFAULT_TYPE, user_id: int, amount: int) -> bool:
    return _store(ctx).spend_balance(user_id, amount)


def _render_history(ctx: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    records = _store(ctx).get_recent_uploads(user_id)
    if not records:
        return "История файлов пуста."

    rows = ["История последних загрузок:"]
    for idx, rec in enumerate(records, start=1):
        rows.append(
            f"{idx}) {rec.created_at} — {rec.filename} (уникальных: {rec.inserted}/{rec.total_lines})"
        )
    return "\n".join(rows)


async def _send_upload_by_history_index(update: Update, context: ContextTypes.DEFAULT_TYPE, index_text: str) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    records = _store(context).get_recent_uploads(user_id)
    if not records:
        await update.message.reply_text("История загрузок пуста.")
        return

    try:
        idx = int(index_text)
    except ValueError:
        await update.message.reply_text("Введите номер файла из истории (например: 1).")
        return

    if idx < 1 or idx > len(records):
        await update.message.reply_text("Неверный номер файла из истории.")
        return

    rec = records[idx - 1]
    if not rec.stored_path:
        await update.message.reply_text("Для этой записи файл недоступен для скачивания.")
        return

    file_path = Path(rec.stored_path)
    if not file_path.exists():
        await update.message.reply_text("Файл не найден на сервере.")
        return

    with file_path.open("rb") as fh:
        await update.message.reply_document(document=fh, filename=rec.filename)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name if update.effective_user else "пользователь"
    user_id = update.effective_user.id if update.effective_user else 0
    kb = _admin_keyboard() if _is_admin(user_id, _settings(context)) else _main_keyboard()
    await update.message.reply_text(await welcome(name), reply_markup=kb)


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Использование: /check <строка>")
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not _try_charge_balance(context, user_id, 1):
        await update.message.reply_text("Недостаточно баланса. Стоимость проверки: $1")
        return

    exists = _store(context).contains(query)
    await update.message.reply_text("✅ Найдено" if exists else "❌ Не найдено")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("Использование: /add <строка>")
        return

    inserted = _store(context).insert_one(value)
    if inserted:
        await update.message.reply_text("✅ Добавлено")
    else:
        await update.message.reply_text("⚠️ Пустая строка или уже существует")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    if not text:
        return

    step = context.user_data.get("step")

    if step == "await_check_query":
        context.user_data["step"] = None
        user_id = update.effective_user.id if update.effective_user else 0
        if not _try_charge_balance(context, user_id, 1):
            await update.message.reply_text("Недостаточно баланса. Стоимость проверки: $1")
            return
        exists = _store(context).contains(text)
        await update.message.reply_text("✅ Найдено" if exists else "❌ Не найдено")
        return

    if step == "await_grant_balance":
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("Формат: <user_id> <amount>")
            return
        try:
            target_user_id = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            await update.message.reply_text("Нужны целые числа: <user_id> <amount>")
            return

        new_balance = _store(context).add_balance(target_user_id, amount)
        context.user_data["step"] = None
        await update.message.reply_text(f"Баланс обновлен. user_id={target_user_id}, новый баланс=${new_balance}")
        return

    if step == "await_download_upload":
        context.user_data["step"] = None
        await _send_upload_by_history_index(update, context, text)
        return

    if text == "📜 Правила":
        await update.message.reply_text(RULES)
        return

    if text == "🛟 Поддержка":
        await update.message.reply_text(SUPPORT)
        return

    if text == "📂 Загрузить файл":
        await update.message.reply_text(f"{SEND_TEXT_FILE}\n{SEND_FILE_LINK}")
        return

    if text == "🔍 Проверить строку":
        context.user_data["step"] = "await_check_query"
        await update.message.reply_text("Отправьте строку для проверки")
        return

    if text == "👤 Профиль":
        user_id = update.effective_user.id if update.effective_user else 0
        balance = _store(context).get_balance(user_id)
        history = _render_history(context, user_id)
        await update.message.reply_text(f"Ваш ID: {user_id}\nБаланс: ${balance}\n\n{history}")
        return

    if text == "📥 Скачать файл":
        user_id = update.effective_user.id if update.effective_user else 0
        history = _render_history(context, user_id)
        if history == "История файлов пуста.":
            await update.message.reply_text(history)
            return

        context.user_data["step"] = "await_download_upload"
        await update.message.reply_text(f"{history}\n\nВведите номер файла из истории для скачивания.")
        return

    if text == "🛠 Админка":
        user_id = update.effective_user.id if update.effective_user else 0
        if not _is_admin(user_id, _settings(context)):
            await update.message.reply_text("У вас нет доступа к админке")
            return

        context.user_data["step"] = "await_grant_balance"
        await update.message.reply_text("Введите: <user_id> <amount> для выдачи баланса в $")
        return

    if "\n" not in text:
        user_id = update.effective_user.id if update.effective_user else 0
        if not _try_charge_balance(context, user_id, 1):
            await update.message.reply_text("Недостаточно баланса. Стоимость проверки: $1")
            return
        exists = _store(context).contains(text)
        await update.message.reply_text("✅ Найдено" if exists else "❌ Не найдено")
        return

    report = import_text_blob(_store(context), text, batch_size=_settings(context).import_batch_size)
    await update.message.reply_text(
        f"Импорт завершён. Строк: {report.total_lines}, добавлено: {report.inserted}, пустых: {report.skipped_empty}."
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    max_size = _settings(context).max_file_size_mb * 1024 * 1024
    if doc.file_size and doc.file_size > max_size:
        await update.message.reply_text(f"Файл слишком большой. Лимит: {_settings(context).max_file_size_mb}MB")
        return

    filename = doc.file_name or "upload.txt"
    if not filename.lower().endswith(".txt"):
        await update.message.reply_text("Поддерживаются только .txt файлы")
        return

    user_id = update.effective_user.id if update.effective_user else 0
    if not _try_charge_balance(context, user_id, 2):
        await update.message.reply_text("Недостаточно баланса. Стоимость проверки файлом: $2")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / filename
        telegram_file = await context.bot.get_file(doc.file_id)
        await telegram_file.download_to_drive(str(path))

        upload_dir = _settings(context).db_path.parent / "uploads" / str(user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = upload_dir / f"{doc.file_id}_{filename}"
        copy2(path, stored_path)

        report = import_txt_file(
            _store(context),
            path,
            batch_size=_settings(context).import_batch_size,
        )

    _store(context).record_upload(user_id, filename, report.inserted, report.total_lines, str(stored_path))

    await update.message.reply_text(WAIT_FOR_CHECK)
    await update.message.reply_text(await upload_processed(report.inserted))


async def post_init(app: Application) -> None:
    settings = load_settings()
    app.bot_data["settings"] = settings
    app.bot_data["store"] = HashStore(settings.db_path)


async def post_shutdown(app: Application) -> None:
    store: HashStore | None = app.bot_data.get("store")
    if store:
        store.close()


def build_app() -> Application:
    settings = load_settings()
    app = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    app = build_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
