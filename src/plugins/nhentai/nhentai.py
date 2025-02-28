import io
import os
import random
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx
from PIL import Image, ImageFilter
from pykeyboard import InlineButton, InlineKeyboard
from pyrogram import Client, filters
from pyrogram.enums.parse_mode import ParseMode
from pyrogram.enums.chat_type import ChatType
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import CallbackQuery, InputMediaPhoto, Message
from structlog import get_logger

from src.config.framework import get_chat_setting
from src.database.client import DatabaseClient
from src.plugins.help import command_handler
from src.security.permissions import requires_setting
from src.security.rate_limiter import rate_limit
from .models import NhentaiGallery
from .service import CollageCreator, NhentaiAPI

# Constants
PROXY_URL: str = f"socks5://{os.getenv('PROXY_HOST')}:{os.getenv('PROXY_PORT')}"
NHENTAI_URL_PATTERN = r"https?://nhentai\.net/g/(\d+)"
MAX_RETRIES = 3

BLACKLIST_TAGS = ["lolicon", "shotacon", "guro", "rape", "scat", "urination", "ryona", "piss drinking", "torture"]

# Message constants
NSFW_DISABLED_MESSAGE = "❌ NSFW контент отключен в этом чате. Администратор может включить его через /config"
NHENTAI_DOWN_MESSAGE = "NHentai недоступен"
NO_RESULTS_MESSAGE = "Не найдено результатов для '{query}'"

log = get_logger(__name__)


class DownloadError(Exception):
    pass


async def get_blur_setting(chat_id: int, message: Message = None) -> bool:
    """Get nhentai_blur setting from peer_config"""
    # Always disable blur (return False) in private chats
    if message and message.chat.type == ChatType.PRIVATE:
        return False
        
    # Otherwise use config value
    return await get_chat_setting(chat_id, "nhentai_blur", True)


async def download_image(url: str, session: httpx.AsyncClient) -> io.BytesIO:
    """Download image from URL to BytesIO"""
    try:
        proxy_enabled = bool(session._transport._pool._proxy_url) if hasattr(session._transport, "_pool") and hasattr(session._transport._pool, "_proxy_url") else False
        log.info("Downloading image", extra={"url": url, "proxy_enabled": proxy_enabled})

        response = await session.get(url)

        if response.status_code == 200:
            content_length = len(response.content)
            log.info("Image downloaded successfully", extra={"url": url, "content_length": content_length, "content_type": response.headers.get("content-type")})
            return io.BytesIO(response.content)
        elif response.status_code == 404:
            log.warning("Image not found", extra={"url": url, "status_code": 404, "response_headers": dict(response.headers)})
            raise DownloadError(f"Image not found at {url}")
        else:
            log.error("Failed to download image", extra={"url": url, "status_code": response.status_code, "response_headers": dict(response.headers), "response_text": response.text if response.headers.get("content-type", "").startswith("text") else None})
            raise DownloadError(f"Failed to download image from {url} with status code {response.status_code}")

    except httpx.TimeoutException as e:
        log.error("Timeout while downloading image", extra={"url": url, "error": str(e), "timeout_seconds": session.timeout.read})
        raise DownloadError(f"Timeout while downloading image from {url}: {str(e)}")
    except httpx.NetworkError as e:
        log.error("Network error while downloading image", extra={"url": url, "error": str(e)})
        raise DownloadError(f"Network error while downloading image from {url}: {str(e)}")
    except Exception as e:
        log.error("Unexpected error while downloading image", extra={"url": url, "error": str(e), "error_type": type(e).__name__})
        raise DownloadError(f"Unexpected error while downloading image from {url}: {str(e)}")


def blur_image(image: io.BytesIO) -> io.BytesIO:
    """Apply blur effect to image"""
    with Image.open(image) as img:
        blurred_img = img.filter(ImageFilter.GaussianBlur(radius=30))
        output = io.BytesIO()
        blurred_img.save(output, format="JPEG")
        output.seek(0)
    return output


def generate_output_message(media: NhentaiGallery, chat_id: int, message: Message = None) -> Tuple[List[InputMediaPhoto], bool]:
    """Generate output message with media and check for blacklisted tags"""
    link = f"https://nhentai.net/g/{media.id}"
    caption = f"<b>№{media.id}</b> | <a href='{link}'><b>{media.title.pretty}</b></a>\n\n"
    caption += f"<b>Pages:</b> {media.num_pages}\n<b>Favorites:</b> {media.num_favorites}\n\n"

    tag_dict: Dict[str, List[str]] = {category: [] for category in ["language", "artist", "group", "parody", "category", "tag"]}
    [tag_dict[tag.type].append(tag.name) for tag in media.tags if tag.type in tag_dict]

    for category, tags in tag_dict.items():
        if tags:
            caption += f"<b>{category.capitalize()}:</b> {', '.join(tags)}\n"

    timestamp_to_date = datetime.fromtimestamp(media.upload_date)
    caption += f"\n<b>Uploaded:</b> {timestamp_to_date.strftime('%Y-%m-%d')}"
    
    # Check if any blacklisted tags are present
    has_blacklisted_tag = any(tag in BLACKLIST_TAGS for tag in tag_dict["tag"])
    
    album = [InputMediaPhoto(media.images.pages[0], caption=caption, parse_mode=ParseMode.HTML)]
    total_pages = len(media.images.pages)
    album.extend([InputMediaPhoto(media.images.pages[min(total_pages - 1, max(1, round(total_pages * p / 100)))]) for p in [15, 30, 50, 70, 90] if total_pages >= len(album) + 1])

    return album, has_blacklisted_tag


async def send_media_group(client: Client, chat_id: int, album: List[InputMediaPhoto], message: Message, use_proxy: bool = False, blur: bool = False) -> Optional[str]:
    """Send media group and return error message if any"""
    try:
        # Check if blur should be applied based on settings
        should_blur = blur and await get_blur_setting(chat_id, message)
        
        if not should_blur:
            await message.reply_media_group(media=album, quote=True)
        else:
            log.warning("Blacklisted tags detected. Downloading, blurring, and resending images...", extra={"proxy_url": PROXY_URL if use_proxy else None})

            client_config = {"timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0), "proxy": PROXY_URL if use_proxy else None, "follow_redirects": True}

            async with httpx.AsyncClient(**client_config) as session:
                new_album = []
                for media in album:
                    try:
                        image = await download_image(media.media, session)
                        blurred_image = blur_image(image)
                        new_media = InputMediaPhoto(blurred_image, caption=media.caption, parse_mode=media.parse_mode)
                        new_album.append(new_media)
                    except Exception as img_e:
                        log.error("Failed to process image", extra={"error": str(img_e), "media_url": media.media, "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
                        raise

            await message.reply_media_group(media=new_album, quote=True)
        return None

    except Exception as e:
        error_msg = str(e)
        if "WEBPAGE" in error_msg:
            try:
                log.warning("Failed to send images by URL. Downloading and resending...", extra={"error": error_msg, "album_size": len(album), "blur_enabled": blur})

                client_config = {"timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0), "proxy": PROXY_URL if use_proxy else None, "follow_redirects": True}

                async with httpx.AsyncClient(**client_config) as session:
                    new_album = []
                    for i, media in enumerate(album):
                        try:
                            image = await download_image(media.media, session)
                            if blur and await get_blur_setting(chat_id, message):
                                image = blur_image(image)
                            new_media = InputMediaPhoto(image, caption=media.caption, parse_mode=media.parse_mode)
                            new_album.append(new_media)
                        except Exception as img_e:
                            log.error(f"Failed to process image {i + 1}/{len(album)}", extra={"error": str(img_e), "media_url": media.media, "blur_enabled": blur})
                            raise

                await message.reply_media_group(media=new_album, quote=True)
                return None
            except Exception as download_e:
                log.error("Failed to download and process images", extra={"error": str(download_e), "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
                return f"Failed to download and send images: {str(download_e)}"

        log.error("Failed to send media group", extra={"error": error_msg, "album_size": len(album), "proxy_enabled": bool(use_proxy), "blur_enabled": blur})
        return f"Failed to send media group: {error_msg}"


@Client.on_message(filters.command(["nhentai"], prefixes="/") & ~filters.channel, group=1)
@requires_setting('nsfw')
@command_handler(commands=["nhentai"], arguments="[необяз. поисковый запрос]", description="Случайная додзинся или поиск по nhentai", group="NSFW")
@rate_limit(
    operation="nhentai_handler",
    window_seconds=15,
    on_rate_limited=lambda message: message.reply("🕒 Подождите 15 секунд перед следующим запросом!")
)
async def nhentai_handler(client: Client, message: Message):
    """Handler for /nhentai command"""
    fetcher = NhentaiAPI()
    
    if len(message.command) <= 1:
        try:
            random_number = random.randint(1, 531925)
            log.info("Fetching random hentai from nhentai.net")

            try:
                media: NhentaiGallery = await fetcher.get_by_id(random_number)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    log.warning(f"Gallery with ID {random_number} not found. Retrying...")
                    return await nhentai_handler(client, message)
                return
            except httpx.ReadTimeout as e:
                log.warning(f"Failed to read response for gallery with ID {random_number}. Is NHentai.net up? {e}")
                await message.reply(NHENTAI_DOWN_MESSAGE, quote=True)
                return

            log.info(f"Fetched random hentai from nhentai.net: {media.title.pretty} - {media.id}")
            album, has_blacklisted_tag = generate_output_message(media, message.chat.id, message)
            error = await send_media_group(client, message.chat.id, album, message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)

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


def truncate_title(title: str, max_length: int = 40) -> str:
    """Truncate title to max length with ellipsis"""
    return (title[: max_length - 3] + "...") if len(title) > max_length else title


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
            truncated_title = truncate_title(result.title.pretty)
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
            await message.reply_photo(
                photo=collage,
                caption=caption,
                reply_markup=keyboard,
                quote=True
            )
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
@rate_limit(
    operation="nhentai_callback",
    window_seconds=30,
    on_rate_limited=lambda callback_query: callback_query.answer("Please wait before requesting another gallery!", show_alert=True)
)
async def nhentai_callback_handler(client: Client, callback_query: CallbackQuery):
    fetcher = NhentaiAPI()
    gallery_id = int(callback_query.data.split(":")[1])
    try:
        # Answer the callback query immediately
        await callback_query.answer("Fetching gallery...")

        media: NhentaiGallery = await fetcher.get_by_id(gallery_id)
        album, has_blacklisted_tag = generate_output_message(media, callback_query.message.chat.id, callback_query.message)

        # Add the requester's mention to the caption of the first image
        requester_mention = callback_query.from_user.mention()
        album[0].caption += f"\n\nRequested by {requester_mention}"

        # First try sending directly with URLs
        error = await send_media_group(client, callback_query.message.chat.id, album, callback_query.message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)
        
        if error and "WEBPAGE_CURL_FAILED" in error:
            log.warning("Failed to send images by URL. Downloading and resending...")
            
            client_config = {"timeout": httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0), "proxy": PROXY_URL if fetcher.use_proxy else None, "follow_redirects": True}
            
            async with httpx.AsyncClient(**client_config) as session:
                new_album = []
                for i, media_item in enumerate(album):
                    try:
                        image = await download_image(media_item.media, session)
                        if has_blacklisted_tag and await get_blur_setting(callback_query.message.chat.id, callback_query.message):
                            image = blur_image(image)
                        new_media = InputMediaPhoto(image, caption=media_item.caption, parse_mode=media_item.parse_mode)
                        new_album.append(new_media)
                    except Exception as img_e:
                        log.error(f"Failed to process image {i + 1}/{len(album)}", extra={"error": str(img_e), "media_url": media_item.media})
                        raise

                await callback_query.message.reply_media_group(media=new_album, quote=True)
        elif error:
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
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                log.warning(f"Gallery with ID {gallery_id} not found. Not sending error message...")
                return
            return
        except httpx.ReadTimeout as e:
            log.warning(f"Failed to read response for gallery with ID {gallery_id}. Is NHentai.net up? {e}")
            await message.reply(NHENTAI_DOWN_MESSAGE, quote=True)
            return

        album, has_blacklisted_tag = generate_output_message(media, message.chat.id, message)
        error = await send_media_group(client, message.chat.id, album, message, use_proxy=fetcher.use_proxy, blur=has_blacklisted_tag)
        if error:
            await message.reply(f"Error: {error}", quote=True)
        return

    except Exception as e:
        log.exception(f"An error occurred while processing nhentai URL: {str(e)}")
        await message.reply(f"An error occurred while processing the nhentai URL: {str(e)}", quote=True)
        return


@Client.on_callback_query(filters.regex(r"^nhentai_page\|(.+)\|(\d+)$"))
@rate_limit(
    operation="nhentai_page",
    window_seconds=30,
    on_rate_limited=lambda callback_query: callback_query.answer("Please wait before changing pages!", show_alert=True)
)
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