from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    db_path: Path
    import_batch_size: int = 5000
    max_file_size_mb: int = 50
    admin_ids: tuple[int, ...] = ()
    audit_chat_ids: tuple[int, ...] = ()



def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    db_path = Path(os.getenv("LMDB_PATH", "./data/antipublic.sqlite3")).resolve()

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = tuple(
        int(value)
        for value in (part.strip() for part in admin_ids_raw.split(","))
        if value
    )

    audit_chat_raw = os.getenv("AUDIT_CHAT_ID", "").strip()
    audit_chat_ids = tuple(
        int(value)
        for value in (part.strip() for part in audit_chat_raw.split(","))
        if value
    )

    return Settings(
        bot_token=token,
        db_path=db_path,
        import_batch_size=int(os.getenv("IMPORT_BATCH_SIZE", "5000")),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "50")),
        admin_ids=admin_ids,
        audit_chat_ids=audit_chat_ids,
    )
