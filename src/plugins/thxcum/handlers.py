"""god forgive me for this"""

import os
from typing import Optional, Tuple

from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

from src.plugins.help import command_handler
from src.plugins.thxcum.service import ThxCumService
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit

# Setup logger
log = get_logger(__name__)

# Error messages
PROCESSING_ERROR = "❌ Произошла ошибка при обработке изображения. Попробуйте позже."
NO_IMAGE_ERROR = "❌ Изображение не найдено. Отправьте изображение, ответьте на сообщение с изображением, или используйте свой аватар."
GIF_UNSUPPORTED = "❌ GIF-изображения не поддерживаются."

# Service initialization
BACKGROUND_PATH = os.path.join("src", "plugins", "thxcum", "assets", "background.png")
TEMPLATE_PATH = os.path.join("src", "plugins", "thxcum", "assets", "template.png")
FONT_PATH = os.path.join("src", "plugins", "thxcum", "assets", "trebuc.ttf")

thxcum_service = ThxCumService(background_path=BACKGROUND_PATH, template_path=TEMPLATE_PATH, font_path=FONT_PATH)


async def check_media_type(message: Message) -> Tuple[bool, bool, bool]:
    """Check if message contains media and what type"""
    has_media = bool(message.photo or message.document)
    is_gif = bool(message.animation or (message.document and message.document.mime_type and "gif" in message.document.mime_type.lower()))
    is_reply = bool(message.reply_to_message)
    return has_media, is_gif, is_reply


async def get_photo(message: Message) -> Tuple[Optional[bytes], Optional[str]]:
    """Extract photo from message"""
    try:
        if message.photo:
            # Download the photo directly
            photo_data = await message.download(in_memory=True)
            return photo_data, None

        if message.document and message.document.mime_type and "image" in message.document.mime_type.lower():
            doc_data = await message.download(in_memory=True)
            return doc_data, None

    except Exception as e:
        log.error(f"Failed to get photo: {str(e)}")

    return None, None


async def get_image_from_message(client: Client, message: Message) -> Optional[bytes]:
    """Extract image from message in various scenarios"""
    has_media, is_gif, is_reply = await check_media_type(message)

    if is_gif:
        await message.reply_text(GIF_UNSUPPORTED, quote=True)
        return None

    try:
        if has_media:
            img, _ = await get_photo(message)
            return img

        if message.reply_to_message:
            # Check if replied message has user photo
            if hasattr(message.reply_to_message.from_user, "photo") and message.reply_to_message.from_user.photo:
                return await client.download_media(message.reply_to_message.from_user.photo.big_file_id, in_memory=True)
            # Check if replied message has media
            img, _ = await get_photo(message.reply_to_message)
            return img

        # Use user's avatar as fallback
        if hasattr(message.from_user, "photo") and message.from_user.photo:
            return await client.download_media(message.from_user.photo.big_file_id, in_memory=True)

    except Exception as e:
        log.error(f"Failed to get image: {str(e)}")

    await message.reply_text(NO_IMAGE_ERROR, quote=True)
    return None


@command_handler(commands=["cum"], description="«Спасибо, я кончил»", group="NSFW", arguments="[необяз. @ пользователя | реплай на картинку]")
@Client.on_message(filters.command(["cum"]), group=2)
@requires_setting("nsfw")
@rate_limit(
    operation="thxcum_handler",
    window_seconds=10,  # One request per 10 seconds
    on_rate_limited=lambda message: message.reply("🕒 Подождите 10 секунд перед следующим запросом!"),
)
async def thxcum_command(client: Client, message: Message):
    """Process an image in ThxCum style and send it back"""
    await message.reply_text("❌ Сервис обработки изображений недоступен.", quote=True)
    # Send initial notification
    notification = await message.reply_text("🔄 Обрабатываем изображение...", quote=True)

    try:
        # Get image from message
        image_data = await get_image_from_message(client, message)
        if not image_data:
            await notification.delete()
            return

        # Process the image
        result = await thxcum_service.process_image(image_data)

        # Send the processed image
        await message.reply_photo(
            photo=result,
            quote=True,
            has_spoiler=True,
        )

        # Delete notification
        await notification.delete()

    except Exception as e:
        log.error(f"Error processing image: {str(e)}")
        await notification.edit_text(f"{PROCESSING_ERROR} Ошибка: {str(e)}")
