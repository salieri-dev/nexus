from datetime import datetime

from pyrogram import Client, filters

from src.plugins.help import command_handler


@Client.on_message(filters.command("ping"), group=1)
@command_handler(commands=["ping"], description="Проверить задержку бота", group="Утилиты")
async def ping_command(client, message):
    start = datetime.now()
    await message.reply_text("Pong!")
    end = datetime.now()
    latency = (end - start).microseconds / 1000
    await message.reply_text(f"Задержка: {latency}ms")
