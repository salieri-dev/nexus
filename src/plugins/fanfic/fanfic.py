from pyrogram import Client, filters
from pyrogram.types import Message

from structlog import get_logger

log = get_logger(__name__)


@Client.on_message(filters.command(["fanfic"]), group=1)
async def fanfic_handler(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ Пожалуйста, укажите тему для фанфика после команды /fanfic", quote=True)
        return
