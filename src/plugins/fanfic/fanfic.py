from datetime import datetime

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.plugins.help import command_handler
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit
from .repository import FanficRepository
from .service import generate_fanfic

log = get_logger(__name__)


@Client.on_message(filters.command(["fanfic"]), group=1)
@requires_setting('nsfw')
@command_handler(commands=["fanfic"], arguments="[тема]", description="Создать фанфик", group="Мемы")
@rate_limit(
    operation="fanfic_handler",
    window_seconds=45,  # One request per 45 seconds
    on_rate_limited=lambda message: message.reply("🕒 Подождите 45 секунд перед следующим запросом!")
)
async def fanfic_handler(client: Client, message: Message):
    """Handler for /fanfic command"""
    db = DatabaseClient.get_instance()
    repository = FanficRepository(db.client)
    config_repo = BotConfigRepository(db_client=db)

    # Validate input
    if len(message.command) < 2:
        await message.reply("❌ Пожалуйста, укажите тему для фанфика после команды /fanfic", quote=True)
        return

    # Get the topic from the command
    topic = " ".join(message.command[1:])
    if len(topic) < 3:
        await message.reply("❌ Тема слишком короткая! Минимум 3 символа.", quote=True)
        return

    # Send initial response
    reply_msg = await message.reply("⚙️ Генерирую фанфик...", quote=True)

    # Generate fanfic using Pydantic model
    fanfic_response = await generate_fanfic(topic)

    if not fanfic_response:
        await reply_msg.edit_text("❌ Не удалось сгенерировать фанфик. Попробуйте позже.")
        return

    # Extract title and content from Pydantic model
    title = fanfic_response.title
    content = fanfic_response.content

    # Format the response
    formatted_response = f"<b>{title}</b>\n\n{content}"

    # Get model name from config
    model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME",
                                                           "anthropic/claude-3.5-sonnet:beta")

    # Store fanfic data in database
    fanfic_record = {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "topic": topic,
        "title": title,
        "content": content,
        "timestamp": datetime.utcnow(),
        "model": model_name,
        "temperature": 0.8
    }
    await repository.save_fanfic(fanfic_record)

    # Send the result
    await reply_msg.delete()

    # Split message if it's too long
    if len(formatted_response) > 4000:
        # Send title and first part
        first_part = formatted_response[:4000]
        await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)

        # Send remaining parts
        remaining = formatted_response[4000:]
        await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
    else:
        await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)
