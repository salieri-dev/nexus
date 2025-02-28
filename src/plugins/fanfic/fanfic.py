"""Fanfic generation command handler"""

from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

from src.plugins.help import command_handler
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit
from .constants import RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_OPERATION, MESSAGES
from .service import FanficService

log = get_logger(__name__)


@Client.on_message(filters.command(["fanfic"]), group=1)
@requires_setting("nsfw")
@command_handler(commands=["fanfic"], arguments="[тема]", description="Создать фанфик", group="Мемы")
@rate_limit(
    operation=RATE_LIMIT_OPERATION,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    on_rate_limited=lambda message: message.reply(MESSAGES["RATE_LIMITED"]),
)
async def fanfic_handler(client: Client, message: Message):
    """Handler for /fanfic command"""
    # Get the topic from the command
    topic = " ".join(message.command[1:]) if len(message.command) > 1 else ""

    # Validate topic
    is_valid, error_message = await FanficService.validate_topic(topic)
    if not is_valid:
        await message.reply(error_message, quote=True)
        return

    # Send initial response
    reply_msg = await message.reply(MESSAGES["WAIT_MESSAGE"], quote=True)

    # Generate fanfic using service
    fanfic_response = await FanficService.generate_fanfic(topic)

    if not fanfic_response:
        await reply_msg.edit_text(MESSAGES["GENERATION_FAILED"])
        return

    # Save to database
    await FanficService.save_fanfic_to_db(topic=topic, fanfic_response=fanfic_response, user_id=message.from_user.id, chat_id=message.chat.id)

    # Format and send the response
    await FanficService.format_and_send_response(message, fanfic_response, reply_msg)
