"""Frontend handlers for nhentai plugin"""

import random
import re
from typing import Optional

from pykeyboard import InlineButton, InlineKeyboard
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import CallbackQuery, Message
from structlog import get_logger

from src.config.framework import get_chat_setting
from src.plugins.help import command_handler
from src.plugins.nhentai.constants import NHENTAI_DOWN_MESSAGE, NHENTAI_URL_PATTERN, NO_RESULTS_MESSAGE
from src.plugins.nhentai.models import NhentaiGallery
from src.plugins.nhentai.service import CollageCreator, NhentaiAPI, NhentaiService
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit

log = get_logger(__name__)


@Client.on_message(filters.command(["nhentai"], prefixes="/") & ~filters.channel, group=1)
@requires_setting("nsfw")
@command_handler(commands=["nhentai"], arguments="[необяз. поисковый запрос]", description="Случайная додзинся или поиск по nhentai", group="NSFW")
@rate_limit(operation="nhentai_handler", window_seconds=5, on_rate_limited=lambda message: message.reply("🕒 Подождите 5 секунд перед следующим запросом!"))
async def nhentai_handler(client: Client, message: Message):
    """Handler for /nhentai command"""
    fetcher = NhentaiAPI()

    if len(message.command) <= 1:
        try:
            random_number = random.randint(1, 531925)
            log.info("Fetching random hentai from nhentai.net")

            try:
                media: NhentaiGallery = await fetcher.get_by_id(random_number)
            except Exception as e:
                if hasattr(e, "response") and hasattr(e.response, "status_code") and e.response.status_code == 404:
                    log.warning(f"Gallery with ID {random_number} not found. Retrying...")
                    return await nhentai_handler(client, message)
                elif "timeout" in str(e).lower():
                    log.warning(f"Failed to read response for gallery with ID {random_number}. Is NHentai.net up? {e}")
                    await message.reply(NHENTAI_DOWN_MESSAGE, quote=True)
                    return
                raise

            log.info(f"Fetched random hentai from nhentai.net: {media.title.pretty} - {media.id}")
            album, has_blacklisted_tag = NhentaiService.generate_output_message(media, message.chat.id, message)
            error = await NhentaiService.send_media_group(client, message.chat.id, album, message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)

            if error:
                await message.reply(f"Error: {error}", quote=True)
            return

        except Exception as e:
            log.exception("A detailed exception occurred in get_random: %s", str(e))
            await message.reply(f"An error occurred while processing your request: {e}", quote=True)
            return
    else:
        query = " ".join(message.command[1:])
        return await send_search_results(client, message, query, page=1)


async def send_search_results(client: Client, message, query: str, page: int):
    """Send search results with pagination"""
    fetcher = NhentaiAPI()
    collage_creator = CollageCreator()
    try:
        search_results = await fetcher.search(query, page=page)
        if not search_results:
            await message.reply(NO_RESULTS_MESSAGE.format(query=query), quote=True)
            return

        search_results = search_results[:24]
        keyboard = InlineKeyboard(row_width=6)  # 6 columns

        # Generate collages
        collage = await collage_creator.create_single_collage_as_bytesio(search_results)

        kb_buttons = []
        caption = f"Search results for '{query}' (Page {page}):\n\n"

        for i, result in enumerate(search_results, 1):
            kb_buttons.append(InlineButton(str(i), f"nhentai:{result.id}"))
            truncated_title = NhentaiService.truncate_title(result.title.pretty)
            caption += f"{i}. {truncated_title}\n"

        # Add buttons in groups of 6
        for i in range(0, len(kb_buttons), 6):
            keyboard.row(*kb_buttons[i : i + 6])

        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineButton("◀️ Previous", f"nhentai_page|{query}|{page - 1}"))
        nav_buttons.append(InlineButton("▶️ Next", f"nhentai_page|{query}|{page + 1}"))
        keyboard.row(*nav_buttons)

        collage.seek(0)  # Ensure we're at the start of the BytesIO buffer

        # Truncate the caption if it's too long
        if len(caption) > 1024:
            caption = caption[:1021] + "..."

        # Check if the message is from a callback query or a new command
        if isinstance(message, Message):
            await message.reply_photo(photo=collage, caption=caption, reply_markup=keyboard, quote=True)
        else:  # It's a CallbackQuery
            await client.send_message(chat_id=message.chat.id, text=caption, reply_markup=keyboard)

        return

    except Exception as e:
        log.exception(f"An error occurred while searching: {str(e)}")
        error_message = f"An error occurred while searching: {str(e)}"
        if isinstance(message, Message):
            await message.reply(error_message, quote=True)
        else:  # It's a CallbackQuery
            await client.send_message(chat_id=message.chat.id, text=error_message)
        return


@Client.on_callback_query(filters.regex(r"^nhentai:(\d+)$"))
@rate_limit(operation="nhentai_callback", window_seconds=30, on_rate_limited=lambda callback_query: callback_query.answer("Please wait before requesting another gallery!", show_alert=True))
async def nhentai_callback_handler(client: Client, callback_query: CallbackQuery):
    fetcher = NhentaiAPI()
    gallery_id = int(callback_query.data.split(":")[1])
    try:
        # Answer the callback query immediately
        await callback_query.answer("Fetching gallery...")

        media: NhentaiGallery = await fetcher.get_by_id(gallery_id)
        album, has_blacklisted_tag = NhentaiService.generate_output_message(media, callback_query.message.chat.id, callback_query.message)

        # Add the requester's mention to the caption of the first image
        requester_mention = callback_query.from_user.mention()
        album[0].caption += f"\n\nRequested by {requester_mention}"

        # First try sending directly with URLs
        error = await NhentaiService.send_media_group(client, callback_query.message.chat.id, album, callback_query.message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)

        if error:
            log.error(f"Failed to send media group: {error}")
            await callback_query.message.reply(f"Error: {error}", quote=True)
        return

    except QueryIdInvalid:
        log.warning("Callback query expired. Ignoring.")
        return
    except Exception as e:
        log.exception(f"An error occurred while processing nhentai callback: {str(e)}")
        try:
            await callback_query.answer(f"An error occurred: {str(e)}", show_alert=True)
        except QueryIdInvalid:
            log.warning("Callback query expired. Unable to show error message.")
        return


@Client.on_message(filters.regex(NHENTAI_URL_PATTERN) & ~filters.channel, group=2)
async def nhentai_url_handler(client: Client, message: Message):
    # Check NSFW permission
    nsfw_enabled = await get_chat_setting(message.chat.id, "nsfw_enabled", False)
    if not nsfw_enabled:
        return

    try:
        match = re.search(NHENTAI_URL_PATTERN, message.text)
        if not match:
            return
        gallery_id = int(match.group(1))
        log.info(f"Detected nhentai URL with gallery ID: {gallery_id}")

        fetcher = NhentaiAPI()
        try:
            media: NhentaiGallery = await fetcher.get_by_id(gallery_id)
        except Exception as e:
            if hasattr(e, "response") and hasattr(e.response, "status_code") and e.response.status_code == 404:
                log.warning(f"Gallery with ID {gallery_id} not found. Not sending error message...")
                return
            elif "timeout" in str(e).lower():
                log.warning(f"Failed to read response for gallery with ID {gallery_id}. Is NHentai.net up? {e}")
                await message.reply(NHENTAI_DOWN_MESSAGE, quote=True)
                return
            raise

        album, has_blacklisted_tag = NhentaiService.generate_output_message(media, message.chat.id, message)
        error = await NhentaiService.send_media_group(client, message.chat.id, album, message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)
        if error:
            await message.reply(f"Error: {error}", quote=True)
        return

    except Exception as e:
        log.exception(f"An error occurred while processing nhentai URL: {str(e)}")
        await message.reply(f"An error occurred while processing the nhentai URL: {str(e)}", quote=True)
        return


@Client.on_callback_query(filters.regex(r"^nhentai_page\|(.+)\|(\d+)$"))
@rate_limit(operation="nhentai_page", window_seconds=30, on_rate_limited=lambda callback_query: callback_query.answer("Please wait before changing pages!", show_alert=True))
async def nhentai_page_callback_handler(client: Client, callback_query: CallbackQuery):
    try:
        _, query, page = callback_query.data.split("|")
        page = int(page)

        # Delete the old message
        try:
            await callback_query.message.delete()
        except Exception as e:
            log.exception(f"Failed to delete message: {e}")
            # Continue execution - deletion failure is not critical

        # Send new search results
        result = await send_search_results(client, callback_query.message, query, page)

        # Answer the callback query to remove the loading state
        await callback_query.answer()

        return result

    except Exception as e:
        log.exception(f"Error in page callback handler: {str(e)}")
        try:
            await callback_query.answer(f"Error: {str(e)}", show_alert=True)
        except QueryIdInvalid:
            log.warning("Callback query expired. Unable to show error message.")
        return
