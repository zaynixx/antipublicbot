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



def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required")

    db_path = Path(os.getenv("LMDB_PATH", "./data/antipublic.sqlite3")).resolve()

    return Settings(
        bot_token=token,
        db_path=db_path,
        import_batch_size=int(os.getenv("IMPORT_BATCH_SIZE", "5000")),
        max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "50")),
    )
