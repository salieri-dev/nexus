"""Fanfic generation command handler"""

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from structlog import get_logger
import httpx

from src.plugins.help import command_handler
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit
from .constants import RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_OPERATION, MESSAGES, MAX_MESSAGE_LENGTH
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

    # Delete the initial "generating" message
    await reply_msg.delete()

    # Extract title and content from Pydantic model
    title = fanfic_response.title
    content = fanfic_response.content
    formatted_response = f"{content}"

    # Generate image for the fanfic FIRST
    try:
        # Update the message to indicate image generation
        image_msg = await message.reply("Генерирую изображение для фанфика...", quote=True)

        # Generate image using FalAI
        image_result = await FanficService.generate_image_with_falai(fanfic_response)

        if image_result and "images" in image_result and len(image_result["images"]) > 0:
            image_url = image_result["images"][0]["url"]

            # Delete the "generating image" message
            await image_msg.delete()

            # Send the image as the FIRST photo reply
            await message.reply_photo(photo=image_url, caption=f"<b>{title}</b>\n\n<i>Сам фанфик находится ниже!</i>", quote=True)

            # Then send the text content
            if len(formatted_response) > MAX_MESSAGE_LENGTH:
                # Send first part
                first_part = formatted_response[:MAX_MESSAGE_LENGTH]
                await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)

                # Send remaining parts
                remaining = formatted_response[MAX_MESSAGE_LENGTH:]
                await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
            else:
                await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)
        else:
            await image_msg.edit_text("Не удалось сгенерировать изображение для фанфика.")

            # Send text content if image generation failed
            if len(formatted_response) > MAX_MESSAGE_LENGTH:
                # Send first part
                first_part = formatted_response[:MAX_MESSAGE_LENGTH]
                await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)

                # Send remaining parts
                remaining = formatted_response[MAX_MESSAGE_LENGTH:]
                await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
            else:
                await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)

    except Exception as e:
        log.error(f"Error generating or sending image: {str(e)}")
        await message.reply(f"Произошла ошибка при генерации изображения: {str(e)}", quote=True)

        # Send text content if image generation failed
        if len(formatted_response) > MAX_MESSAGE_LENGTH:
            # Send first part
            first_part = formatted_response[:MAX_MESSAGE_LENGTH]
            await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)

            # Send remaining parts
            remaining = formatted_response[MAX_MESSAGE_LENGTH:]
            await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
        else:
            await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)
