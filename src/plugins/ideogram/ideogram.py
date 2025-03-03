"""Ideogram image generation command handler."""

from typing import Dict, Any, List

from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message, InputMediaPhoto
from structlog import get_logger

from src.config.framework import is_vip
from src.plugins.help import command_handler
from src.database.client import DatabaseClient
from src.database.repository.ratelimit_repository import RateLimitRepository
from src.database.repository.requests_repository import RequestRepository
from src.services.falai import FalAI
from .constants import MODEL_NAME

log = get_logger(__name__)

# Initialize the request repository
request_repository = RequestRepository()


@Client.on_message(filters.command(["ideogram"]), group=1)
@command_handler(commands=["ideogram"], description="Сгенерировать логотип", arguments="[текст]", group="Нейронки")
async def ideogram_command(client: Client, message: Message):
    """Handler for /ideogram command."""
    try:
        # Check if there's a prompt after the command
        if len(message.command) > 1:
            # Apply rate limiting
            user_id = message.from_user.id
            isvip = await is_vip(user_id)
            log.info("VIP Status", user_id=user_id, isvip=isvip)
            
            if isvip:
                log.info("VIP bypassed rate limit for ideogram", user_id=user_id)
            else:
                db_client = DatabaseClient.get_instance()
                rate_limit_repo = RateLimitRepository(db_client)
                
                # Check if user is rate limited (15 seconds window)
                allowed = await rate_limit_repo.check_rate_limit(
                    user_id=user_id,
                    operation="ideogram",
                    window_seconds=90 
                )
                
                if not allowed:
                    await message.reply(
                        "⏳ **Слишком много запросов!**\n\nПожалуйста, подождите 15 секунд перед следующей генерацией изображений.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
            # Get the prompt from the message
            prompt = " ".join(message.command[1:])

            # Send a processing message
            processing_msg = await message.reply("🔄 **Генерация изображений с Ideogram...**\n\nЭто может занять некоторое время.", parse_mode=ParseMode.MARKDOWN)

            # Initialize the repository
            await request_repository.initialize()

            # Prepare payload for the API
            payload = {
                "prompt": prompt
            }

            # Create a request record with initial status
            request_doc = await request_repository.create_request(
                req_type="ideogram",
                user_id=user_id,
                chat_id=message.chat.id,
                prompt=prompt,
                config={},  # No specific config for ideogram
                payload=payload,
                status="processing"
            )

            # Get FalAI client
            falai = FalAI()

            # Generate images
            image_urls = []
            error = None
            try:
                # Submit the job to fal-ai
                log.info("Submitting ideogram generation job", user_id=user_id, prompt=prompt)
                result = await falai.generate_image_sync(
                    MODEL_NAME,
                    {
                        "prompt": prompt,
                    }
                )
                log.info("Received ideogram generation result", result=result)
                
                # Extract image URLs from the result
                # Ideogram returns a response with an "images" array where each image has a "url" property
                if "images" in result:
                    image_urls = [img.get("url") for img in result.get("images") if img.get("url")]
                    log.info("Extracted image URLs from images array", count=len(image_urls))
                else:
                    log.warning("Unexpected response format from Ideogram", result=result)
                
                # Update the request record with success status and image URLs
                if request_doc and image_urls:
                    await request_repository.update_request(
                        str(request_doc["_id"]),
                        image_urls=image_urls,
                        status="success"
                    )
            except Exception as e:
                log.error("Error generating images with Ideogram", error=str(e), user_id=user_id, prompt=prompt)
                error = str(e)
                
                # Update the request record with failure status and error message
                if request_doc:
                    await request_repository.update_request(
                        str(request_doc["_id"]),
                        error=error,
                        status="failure"
                    )

            if error or not image_urls:
                await processing_msg.edit_text("❌ **Не удалось сгенерировать изображения.**\n\nПожалуйста, попробуйте другой промпт.", parse_mode=ParseMode.MARKDOWN)
                return

            # Create caption
            seed = result.get("seed", "N/A")
            caption = (
                f"**Промпт:** `{prompt}`\n"
                f"**Seed:** `{seed}`\n"
            )

            # Create media group
            media_group = []
            for i, url in enumerate(image_urls):
                # Add caption only to the first image
                media_caption = caption if i == 0 else None
                media_group.append(InputMediaPhoto(url, caption=media_caption, parse_mode=ParseMode.MARKDOWN))

            # Send the media group
            await client.send_media_group(chat_id=message.chat.id, media=media_group, reply_to_message_id=message.id)

            # Delete the processing message
            await processing_msg.delete()
        else:
            # No prompt provided
            await message.reply("⚙️ **Генерация изображений с Ideogram**\n\nИспользуйте `/ideogram [промпт]` для генерации изображений.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.error("Error handling ideogram command", error=str(e))
        await message.reply(f"❌ Произошла ошибка: {str(e)}")