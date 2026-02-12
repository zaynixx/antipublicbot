from __future__ import annotations

import tempfile
from pathlib import Path

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .importers import import_text_blob, import_txt_file
from .storage import HashStore


def _store(ctx: ContextTypes.DEFAULT_TYPE) -> HashStore:
    return ctx.application.bot_data["store"]


def _settings(ctx: ContextTypes.DEFAULT_TYPE) -> Settings:
    return ctx.application.bot_data["settings"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я anti-public бот.\n\n"
        "Команды:\n"
        "/check <строка> — проверить наличие\n"
        "/add <строка> — добавить 1 строку\n"
        "/stats — статистика\n\n"
        "Также можно прислать обычный текст или .txt файл до 50MB."
    )
    await update.message.reply_text(text)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stat = _store(context).stat()
    await update.message.reply_text(
        "\n".join(
            [
                f"Entries: {stat['entries']}",
                f"Map size: {stat['map_size']}",
                f"Last page: {stat['last_pgno']}",
            ]
        )
    )


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Использование: /check <строка>")
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

    if "\n" not in text:
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

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / filename
        telegram_file = await context.bot.get_file(doc.file_id)
        await telegram_file.download_to_drive(str(path))

        report = import_txt_file(
            _store(context),
            path,
            batch_size=_settings(context).import_batch_size,
        )

    await update.message.reply_text(
        "\n".join(
            [
                "Файл обработан.",
                f"Строк: {report.total_lines}",
                f"Добавлено: {report.inserted}",
                f"Пустых: {report.skipped_empty}",
            ]
        )
    )


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
    app.add_handler(CommandHandler("stats", stats))
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
