# AntiPublic Telegram Bot

Высокопроизводительный Telegram-бот для работы с большой базой (до 100+ млн строк).

## Что умеет
- Добавлять строки в базу из обычных сообщений.
- Добавлять строки из `.txt` файлов (до лимита `MAX_FILE_SIZE_MB`, по умолчанию 50MB).
- Проверять отдельные строки на наличие в базе (без списания баланса).
- Быстро работать на очень больших объемах за счёт:
  - хэширования строк (`blake2b`, 16 байт ключ),
  - key-value хранения в **SQLite (WAL) + индекс по хэшу**,
  - пакетных транзакций и дедупликации.

## Архитектура
- `src/storage.py` — слой хранения SQLite.
- `src/importers.py` — потоковый импорт строк из текста/файла.
- `src/bot.py` — Telegram-бот (`python-telegram-bot` v21+, async).
- `src/config.py` — настройки через env.

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Впишите BOT_TOKEN
python -m src.bot
```

## Деплой на VPS (Ubuntu 22.04)

Ниже практичный вариант через `systemd`, чтобы бот автоматически стартовал после перезагрузки и перезапускался при сбоях.

### 1) Подготовка сервера

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Создайте отдельного системного пользователя для бота:

```bash
sudo adduser --system --group --home /opt/antipublicbot antipublicbot
```

### 2) Клонирование проекта и установка зависимостей

```bash
sudo -u antipublicbot -H bash -lc '
cd /opt/antipublicbot
git clone <ВАШ_REPO_URL> app
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
'
```

### 3) Настройка окружения

Создайте `.env`:

```bash
sudo -u antipublicbot -H bash -lc '
cd /opt/antipublicbot/app
cat > .env << "EOF"
BOT_TOKEN=123456:your_real_bot_token
LMDB_PATH=/opt/antipublicbot/app/data/antipublic.sqlite3
IMPORT_BATCH_SIZE=5000
MAX_FILE_SIZE_MB=50
EOF
'
```

Создайте директорию под БД:

```bash
sudo -u antipublicbot mkdir -p /opt/antipublicbot/app/data
```

### 4) (Опционально) Первичная загрузка большой базы

Если у вас уже есть большие `.txt` файлы, импортируйте локально на VPS:

```bash
sudo -u antipublicbot -H bash -lc '
cd /opt/antipublicbot/app
source .venv/bin/activate
python -m src.bootstrap /path/to/base.txt
'
```

### 5) Создание systemd-сервиса

Создайте файл `/etc/systemd/system/antipublicbot.service`:

```ini
[Unit]
Description=AntiPublic Telegram Bot
After=network.target

[Service]
Type=simple
User=antipublicbot
Group=antipublicbot
WorkingDirectory=/opt/antipublicbot/app
EnvironmentFile=/opt/antipublicbot/app/.env
ExecStart=/opt/antipublicbot/app/.venv/bin/python -m src.bot
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Примените и запустите:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now antipublicbot
```

### 6) Проверка и полезные команды

Статус сервиса:

```bash
sudo systemctl status antipublicbot
```

Логи в реальном времени:

```bash
sudo journalctl -u antipublicbot -f
```

Перезапуск после обновления:

```bash
sudo systemctl restart antipublicbot
```

### 7) Обновление бота

```bash
sudo -u antipublicbot -H bash -lc '
cd /opt/antipublicbot/app
git pull
source .venv/bin/activate
pip install -e .
'
sudo systemctl restart antipublicbot
```

## Переменные окружения
- `BOT_TOKEN` — токен Telegram-бота (обязательно).
- `LMDB_PATH` — путь к SQLite базе (по умолчанию `./data/antipublic.sqlite3`).
- `IMPORT_BATCH_SIZE` — размер батча вставки (по умолчанию `5000`).
- `MAX_FILE_SIZE_MB` — максимальный размер `.txt` файла (по умолчанию `50`).
- `AUDIT_CHAT_ID` — один или несколько ID приватных чатов/групп через запятую для получения всех проверок строк и загруженных файлов (опционально).


## Как залить вашу существующую `.txt` базу

Если база большая, **лучше загружать её локально на сервере**, а не через Telegram:

```bash
python -m src.bootstrap /path/to/base.txt
```

Можно указать несколько файлов и свои параметры:

```bash
python -m src.bootstrap /data/part1.txt /data/part2.txt \
  --db-path ./data/antipublic.sqlite3 \
  --batch-size 10000
```

После импорта запускайте бота как обычно:

```bash
python -m src.bot
```

> Через Telegram остаётся доступна загрузка `.txt` (10KB–50MB), но для первоначальной заливки десятков/сотен миллионов строк используйте `src.bootstrap` — это быстрее и стабильнее.

> Важно: Telegram Bot API может вернуть `BadRequest: File is too big` для крупных файлов (ограничение зависит от инфраструктуры Telegram). Бот покажет понятную ошибку; для больших баз используйте `python -m src.bootstrap`.

## Как использовать в Telegram
- `/start` — справка.
- `/stats` — статистика базы.
- `/check <строка>` — проверить наличие строки в базе.
- `/add <строка>` — добавить одну строку.
- Просто текстовое сообщение:
  - 1 строка → проверка,
  - несколько строк → пакетное добавление.
- Отправка `.txt` файла → построчный импорт.

## Производительность и масштаб 100M+
1. **Храним только хэш** нормализованной строки — значительно снижает объём.
2. **Потоковый импорт** без загрузки всего файла в RAM.
3. **Пакетные записи** в SQLite в одной транзакции.
4. Для очень высокой нагрузки можно вынести ingestion в отдельный процесс и шардировать данные по префиксу хэша.

## Ограничения
- В текущей реализации значения не хранят исходный текст (только отпечаток). Это оптимально для задач вида "есть/нет".
- Если нужна защита от коллизий выше текущей, можно увеличить длину ключа (например, 20/32 байт).
