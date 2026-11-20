"""合併版的文字記錄：用語音 bot 的帳號，跑原本文字 bot（discord_bot/bot.py）的記錄功能。

    discord_bot/.venv/Scripts/python.exe team_bot/text_logger.py

（通常不用自己跑，`node team_bot/start.mjs` 會一起啟動。）

- token 和伺服器 ID 讀 voice_bot/.env，和語音 bot 同一個帳號。
- 指令全部由 voice_bot 註冊；這裡不註冊任何指令，否則會把 /record、/meeting 蓋掉。
- 原本的 discord_bot/bot.py 沒有改，還是可以用它自己的 token 單獨跑。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "discord_bot"))  # discord_bot's modules import each other by name

import discord  # noqa: E402
from discord import app_commands  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

from bot import BotClient  # noqa: E402
from message_store import MessageStore  # noqa: E402


class TextLogger(BotClient):
    """The text bot's logging, without commands (voice_bot owns every command of this bot account)."""

    async def setup_hook(self) -> None:
        async def ignore_other_commands(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
            if not isinstance(error, app_commands.CommandNotFound):  # /record, /meeting: voice_bot answers
                logging.error("指令錯誤：%s", error)

        self.tree.on_error = ignore_other_commands
        logging.info("文字記錄：不註冊指令（指令由 voice_bot 負責）")


def main() -> None:
    values = dotenv_values(REPO_ROOT / "voice_bot" / ".env")  # never printed
    token = (values.get("DISCORD_TOKEN") or "").strip()
    guild_id = (values.get("DISCORD_GUILD_ID") or "").strip()
    if not token or not guild_id.isdecimal():
        raise SystemExit("voice_bot/.env 要有 DISCORD_TOKEN 和 DISCORD_GUILD_ID")
    db = REPO_ROOT / ((values.get("BOT_DB") or "").strip() or "discord_bot/data/messages.sqlite3")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    client = TextLogger(int(guild_id), MessageStore(db))
    try:
        client.run(token, log_handler=None)
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "Developer Portal 還沒幫這個 bot 開 Message Content Intent 和 Server Members Intent，"
            "文字記錄沒有啟動（語音和指令不受影響）。開法見 team_bot/README.md。"
        )


if __name__ == "__main__":
    main()
