from __future__ import annotations

import csv
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from html import escape
from shutil import copy2

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings, load_settings
from .importers import import_text_blob, import_txt_file
from .storage import HashStore


async def welcome(name: str) -> str:
    return (
        f"👋 Добро пожаловать, {name}!\n"
        "Это бот для проверки и приема строк Login.microsoftonline.com.\n"
        "Работаем аккуратно, прозрачно и по понятным правилам."
    )


SUPPORT = """🛟 Поддержка: @rezer_2281
Если возникнут вопросы — обязательно поможем."""

RULES = """📜 Правила работы
Используя бота, вы подтверждаете, что:
• согласны с правилами проверки,
• принимаете результаты проверки,
• соблюдаете уважительное общение.

Как проходит обработка:
1) Загружаем строки и проверяем уникальность в базе.
2) Очищаем мусор и приводим формат к валидному виду.
3) Прогоняем через рабочий чекер и приватные прокси.

По всем вопросам: @rezer_2281"""

SEND_TEXT_FILE = "📂 Отправьте текстовый файл с аккаунтами в формате: mail:password."
SEND_FILE_LINK = "Принимаются файлы вида passwords.txt"
WAIT_FOR_CHECK = "⏳ Файл принят в обработку. Проверяю строки на уникальность..."
FILE_TOO_BIG_MSG = (
    "❌ Файл слишком большой для обработки через Telegram Bot API. "
    "Попробуйте файл поменьше или загрузите его локально через `python -m src.bootstrap`"
)
FILE_UPLOAD_ERROR_MSG = (
    "❌ Не удалось обработать файл. Проверьте, что это корректный текстовый .txt файл, "
    "и попробуйте снова."
)

ADMIN_HELP = """🛠 Админ-панель
Доступные действия:
• 💳 Выдать баланс — начислить средства пользователю.
• 🧾 Отчет по пользователю — подробная статистика и уникальные поисковые строки.
• 👥 Список пользователей — пользователи, замеченные в системе.
• 📦 Выгрузка пользователя — полный экспорт файлов и всех строк пользователя."""


async def upload_processed(unique_count: int) -> str:
    return (
        "✅ Обработка завершена.\n"
        f"Уникальных строк добавлено: {unique_count}\n"
        "Файл принят в работу ожидайте результатов"
    )


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📜 Правила"), KeyboardButton("🛟 Поддержка")],
            [KeyboardButton("📂 Загрузить файл"), KeyboardButton("🔍 Проверить строку")],
            [KeyboardButton("👤 Профиль")],
        ],
        resize_keyboard=True,
    )


def _admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📜 Правила"), KeyboardButton("🛟 Поддержка")],
            [KeyboardButton("📂 Загрузить файл"), KeyboardButton("🔍 Проверить строку")],
            [KeyboardButton("👤 Профиль")],
            [KeyboardButton("🛠 Админка")],
        ],
        resize_keyboard=True,
    )


def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💳 Выдать баланс", callback_data="admin:grant_balance")],
            [InlineKeyboardButton("🧾 Отчет по пользователю", callback_data="admin:user_report")],
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin:list_users")],
            [InlineKeyboardButton("📦 Выгрузка пользователя", callback_data="admin:export_user")],
        ]
    )


def _store(ctx: ContextTypes.DEFAULT_TYPE) -> HashStore:
    return ctx.application.bot_data["store"]


def _settings(ctx: ContextTypes.DEFAULT_TYPE) -> Settings:
    return ctx.application.bot_data["settings"]


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_ids



def _render_user_admin_report(ctx: ContextTypes.DEFAULT_TYPE, target_user_id: int) -> str:
    store = _store(ctx)
    stats = store.get_user_stats(target_user_id)
    recent_uploads = store.get_recent_uploads(target_user_id, limit=5)
    recent_checks = store.get_recent_checks(target_user_id, limit=10)
    unique_checks = store.get_unique_checked_queries(target_user_id, limit=20)

    lines = [
        f"🧾 Детальный отчет по user_id={target_user_id}",
        f"Баланс: ${stats['balance']}",
        (
            "Файлы: "
            f"{stats['uploads_count']} шт., строк всего: {stats['uploads_total_lines']}, "
            f"уникально добавлено: {stats['uploads_total_inserted']}"
        ),
        f"Проверок строк: {stats['checks_count']} (найдено: {stats['checks_found']}, не найдено: {stats['checks_not_found']})",
        f"Уникальных поисковых строк: {stats['unique_checks_count']}",
        "",
        "Последние загрузки:",
    ]

    if recent_uploads:
        for rec in recent_uploads:
            lines.append(
                f"• {rec.created_at} — {rec.filename} (уникальных: {rec.inserted}/{rec.total_lines})"
            )
    else:
        lines.append("• Нет загрузок.")

    lines.append("")
    lines.append("Последние проверки:")
    if recent_checks:
        for check in recent_checks:
            status = "✅" if check.found else "❌"
            lines.append(f"• {check.created_at} {status} {check.query}")
    else:
        lines.append("• Нет проверок.")

    lines.append("")
    lines.append("Уникальные строки из поисков (до 20):")
    if unique_checks:
        for idx, query in enumerate(unique_checks, start=1):
            lines.append(f"{idx}. {query}")
    else:
        lines.append("• Нет уникальных поисковых строк.")

    return "\n".join(lines)


def _record_check(ctx: ContextTypes.DEFAULT_TYPE, user_id: int, query: str, found: bool) -> None:
    _store(ctx).record_check(user_id, query, found)


def _touch_user(ctx: ContextTypes.DEFAULT_TYPE, update: Update) -> None:
    user = update.effective_user
    if not user:
        return
    _store(ctx).touch_user(user.id, user.username)


def _render_user_link(user_id: int, username: str) -> str:
    clean_username = escape(username.strip().lstrip("@"))
    if clean_username:
        return f"<a href=\"https://t.me/{clean_username}\">@{clean_username}</a>"
    return f"<a href=\"tg://user?id={user_id}\">профиль</a>"


async def _send_audit_message(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    action: str,
    details: str,
) -> None:
    chat_ids = _settings(ctx).audit_chat_ids
    if not chat_ids:
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    user_repr = f"@{username}" if username else "(без username)"
    text = (
        f"🔔 {action}\n"
        f"👤 user_id: <code>{user_id}</code> {user_repr}\n"
        f"🕒 {timestamp}\n"
        f"ℹ️ {details}"
    )
    for chat_id in chat_ids:
        try:
            await ctx.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
        except TelegramError:
            continue


async def _send_audit_file(
    ctx: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    username: str,
    filename: str,
    source_path: Path,
    total_lines: int,
    inserted: int,
) -> None:
    chat_ids = _settings(ctx).audit_chat_ids
    if not chat_ids:
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    user_repr = f"@{username}" if username else "(без username)"
    caption = (
        "📥 Новый загруженный файл\n"
        f"👤 user_id: <code>{user_id}</code> {user_repr}\n"
        f"🕒 {timestamp}\n"
        f"📄 filename: {escape(filename)}\n"
        f"📊 строк: {total_lines}, уникальных: {inserted}"
    )
    unique_lines_filename = f"{Path(filename).stem}_unique.txt"
    unique_lines_payload = _extract_unique_lines_payload(source_path)

    try:
        with source_path.open("rb") as fh:
            payload = fh.read()
    except OSError:
        return

    for chat_id in chat_ids:
        try:
            await ctx.bot.send_document(chat_id=chat_id, document=payload, filename=filename, caption=caption, parse_mode=ParseMode.HTML)
            if unique_lines_payload is not None:
                await ctx.bot.send_document(
                    chat_id=chat_id,
                    document=unique_lines_payload,
                    filename=unique_lines_filename,
                    caption="📄 Уникальные строки из загруженного файла",
                )
        except TelegramError:
            continue


def _extract_unique_lines_payload(source_path: Path) -> bytes | None:
    try:
        raw = source_path.read_bytes()
    except OSError:
        return None

    content: str | None = None
    for encoding in ("utf-8-sig", "utf-16", "cp1251"):
        try:
            content = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if content is None:
        content = raw.decode("latin-1", errors="ignore")

    seen: set[str] = set()
    unique_lines: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line in seen:
            continue
        seen.add(line)
        unique_lines.append(line)

    if not unique_lines:
        return None

    return "\n".join(unique_lines).encode("utf-8")


async def _run_check(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    exists = _store(context).contains(query)
    _record_check(context, user_id, query, exists)
    await update.message.reply_text("✅ Найдено" if exists else "❌ Не найдено")

    if not exists:
        _store(context).insert_one(query)

    username = update.effective_user.username if update.effective_user else ""
    status = "Найдено" if exists else "Не найдено"
    await _send_audit_message(context, user_id, username or "", "Проверка строки", f"Запрос: <code>{escape(query)}</code> | Результат: {status}")



async def _export_user_data(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int) -> None:
    store = _store(context)
    uploads = store.get_all_uploads(target_user_id)
    checks = store.get_all_checks(target_user_id)
    unique_queries = store.get_all_unique_checked_queries(target_user_id)
    stats = store.get_user_stats(target_user_id)

    await update.message.reply_text("⏳ Формирую полный экспорт. Это может занять немного времени...")

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / f"user_{target_user_id}_export"
        root.mkdir(parents=True, exist_ok=True)

        summary_path = root / "summary.txt"
        summary_path.write_text(_render_user_admin_report(context, target_user_id), encoding="utf-8")

        checks_path = root / "checks_all.csv"
        with checks_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "created_at", "found", "query", "normalized_query"])
            for check in checks:
                writer.writerow([check.id, check.created_at, int(check.found), check.query, check.normalized_query])

        queries_path = root / "queries_unique.txt"
        queries_path.write_text("\n".join(unique_queries), encoding="utf-8")

        uploads_path = root / "uploads_all.csv"
        with uploads_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "created_at", "filename", "inserted", "total_lines", "stored_path"])
            for rec in uploads:
                writer.writerow([rec.id, rec.created_at, rec.filename, rec.inserted, rec.total_lines, rec.stored_path])

        files_dir = root / "uploaded_files"
        files_dir.mkdir(exist_ok=True)
        copied_files = 0
        for rec in uploads:
            if not rec.stored_path:
                continue
            source = Path(rec.stored_path)
            if not source.exists() or not source.is_file():
                continue
            safe_name = f"{rec.id}_{source.name}"
            copy2(source, files_dir / safe_name)
            copied_files += 1

        manifest_path = root / "export_manifest.txt"
        manifest_path.write_text(
            (
                f"user_id={target_user_id}\n"
                f"balance=${stats['balance']}\n"
                f"uploads_count={stats['uploads_count']}\n"
                f"checks_count={stats['checks_count']}\n"
                f"unique_queries={stats['unique_checks_count']}\n"
                f"copied_uploaded_files={copied_files}\n"
            ),
            encoding="utf-8",
        )

        archive_path = Path(tmpdir) / f"user_{target_user_id}_full_export.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in root.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, arcname=file_path.relative_to(root))

        with archive_path.open("rb") as fh:
            await update.message.reply_document(
                document=fh,
                filename=archive_path.name,
                caption="📦 Полный экспорт готов: все проверки, уникальные запросы, история загрузок и сохраненные файлы.",
            )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(context, update)
    name = update.effective_user.first_name if update.effective_user else "пользователь"
    user_id = update.effective_user.id if update.effective_user else 0
    kb = _admin_keyboard() if _is_admin(user_id, _settings(context)) else _main_keyboard()
    await update.message.reply_text(await welcome(name), reply_markup=kb)


async def check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(context, update)
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text("Использование: /check <строка>")
        return

    await _run_check(update, context, query)


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(context, update)
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
    _touch_user(context, update)
    text = (update.message.text or "").strip()
    if not text:
        return

    step = context.user_data.get("step")

    if step == "await_check_query":
        context.user_data["step"] = None
        await _run_check(update, context, text)
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
        await update.message.reply_text(f"✅ Баланс обновлен. user_id={target_user_id}, новый баланс=${new_balance}")
        return

    if step == "await_admin_user_report":
        try:
            target_user_id = int(text)
        except ValueError:
            await update.message.reply_text("Введите корректный user_id (целое число).")
            return

        context.user_data["step"] = None
        await update.message.reply_text(_render_user_admin_report(context, target_user_id))
        return

    if step == "await_admin_export_user":
        try:
            target_user_id = int(text)
        except ValueError:
            await update.message.reply_text("Введите корректный user_id (целое число).")
            return

        context.user_data["step"] = None
        await _export_user_data(update, context, target_user_id)
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
        await update.message.reply_text(f"👤 Ваш ID: {user_id}\n💰 Баланс: ${balance}")
        return

    if text == "🛠 Админка":
        user_id = update.effective_user.id if update.effective_user else 0
        if not _is_admin(user_id, _settings(context)):
            await update.message.reply_text("У вас нет доступа к админке")
            return

        context.user_data["step"] = None
        await update.message.reply_text(ADMIN_HELP, reply_markup=_admin_keyboard())
        await update.message.reply_text("Выберите действие:", reply_markup=_admin_panel_keyboard())
        return

    if "\n" not in text:
        await _run_check(update, context, text)
        return

    report = import_text_blob(_store(context), text, batch_size=_settings(context).import_batch_size)
    await update.message.reply_text(
        f"Импорт завершён. Строк: {report.total_lines}, добавлено: {report.inserted}, пустых: {report.skipped_empty}."
    )


async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _touch_user(context, update)
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

    try:
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
    except BadRequest as exc:
        if "File is too big" in str(exc):
            await update.message.reply_text(FILE_TOO_BIG_MSG)
            return
        await update.message.reply_text(FILE_UPLOAD_ERROR_MSG)
        return
    except (OSError, UnicodeError, TelegramError):
        await update.message.reply_text(FILE_UPLOAD_ERROR_MSG)
        return

    _store(context).record_upload(user_id, filename, report.inserted, report.total_lines, str(stored_path))

    await update.message.reply_text(WAIT_FOR_CHECK)
    await update.message.reply_text(await upload_processed(report.inserted))
    username = update.effective_user.username if update.effective_user else ""
    await _send_audit_file(context, user_id, username or "", filename, stored_path, report.total_lines, report.inserted)


async def on_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    await query.answer()
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id, _settings(context)):
        await query.message.reply_text("У вас нет доступа к админке")
        return

    action = query.data or ""
    context.user_data["step"] = None

    if action == "admin:grant_balance":
        context.user_data["step"] = "await_grant_balance"
        await query.message.reply_text("Введите: <user_id> <amount> для выдачи баланса в $")
        return

    if action == "admin:user_report":
        context.user_data["step"] = "await_admin_user_report"
        await query.message.reply_text("Введите user_id пользователя для подробного отчета.")
        return

    if action == "admin:export_user":
        context.user_data["step"] = "await_admin_export_user"
        await query.message.reply_text("Введите user_id пользователя для полного экспорта данных.")
        return

    if action == "admin:list_users":
        users = _store(context).list_known_users(limit=100)
        if not users:
            await query.message.reply_text("В системе пока нет пользователей с активностью.")
            return
        rendered = "\n".join(
            f"{user.user_id} — {_render_user_link(user.user_id, user.username)}"
            for user in users
        )
        await query.message.reply_text(
            f"👥 Пользователи (до 100):\n{rendered}",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
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
    app.add_handler(CommandHandler("check", check))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CallbackQueryHandler(on_admin_callback, pattern=r"^admin:"))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def main() -> None:
    app = build_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
