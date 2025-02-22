from pyrogram import Client, filters
from datetime import datetime

@Client.on_message(filters.command("ping"))
async def ping_command(client, message):
    start = datetime.now()
    await message.reply_text("Pong!")
    end = datetime.now()
    latency = (end - start).microseconds / 1000
    await message.reply_text(f"Latency: {latency}ms")