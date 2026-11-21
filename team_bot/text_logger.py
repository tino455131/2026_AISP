"""合併版的文字記錄：用語音 bot 的帳號，跑文字 bot（text_bot/bot.py）的記錄功能。

    text_bot/.venv/Scripts/python.exe team_bot/text_logger.py

（通常不用自己跑，`node team_bot/start.mjs` 會一起啟動。）

- 設定讀根目錄的 .env：token 用 VOICE_BOT_TOKEN（和語音 bot 同一個帳號），伺服器用 DISCORD_GUILD_ID，
  資料庫用 BOT_DB（沒填就是 data/messages.sqlite3，和其他元件同一個，都透過 sqlite_api 讀寫）。
- 指令全部由 voice_bot 註冊；這裡不註冊任何指令，否則會把 /record、/meeting、/ai 蓋掉。
- text_bot/bot.py 沒有改，還是可以用它自己的 TEXT_BOT_TOKEN 單獨跑（不要和合併版同時跑，訊息會記兩次）。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# sqlite_api sits at the repo root (also installed with `pip install -e .`); text_bot's modules import each other by name.
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "text_bot")]

import discord  # noqa: E402
from discord import app_commands  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from bot import BotClient  # noqa: E402
from sqlite_api import PROJECT_ROOT, SQLiteStore, resolve_database_path  # noqa: E402


class TextLogger(BotClient):
    """The text bot's logging, without commands (voice_bot owns every command of this bot account)."""

    async def setup_hook(self) -> None:
        async def ignore_other_commands(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            if not isinstance(error, app_commands.CommandNotFound):  # /record, /meeting, /ai: voice_bot answers
                logging.error("指令錯誤：%s", error)

        self.tree.on_error = ignore_other_commands
        logging.info("文字記錄：不註冊指令（指令由 voice_bot 負責）")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)  # values are never printed
    token = os.getenv("VOICE_BOT_TOKEN", "").strip()
    guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
    if not token or not guild_id.isdecimal():
        raise SystemExit("根目錄 .env 要有 VOICE_BOT_TOKEN 和 DISCORD_GUILD_ID（合併版用語音 bot 的帳號）")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    client = TextLogger(int(guild_id), SQLiteStore(resolve_database_path(os.getenv("BOT_DB"))))
    try:
        client.run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "Developer Portal 還沒幫這個 bot 開 Message Content Intent 和 Server Members Intent，"
            "文字記錄沒有啟動（語音和指令不受影響）。開法見 team_bot/README.md。"
        )


if __name__ == "__main__":
    main()
