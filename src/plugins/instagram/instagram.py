import re

from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message
from structlog import get_logger

from src.plugins.instagram.service import InstagramMediaFetcher
from src.security.rate_limiter import rate_limit
from src.utils.credentials import Credentials

log = get_logger(__name__)


def extract_instagram_code(url):
    pattern = r"/([A-Za-z0-9_-]{11})/?"
    match = re.search(pattern, url)
    return match.group(1) if match else None


instagram_url_pattern = r"https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+"


# async def handle_rate_limit(event: Message):
#     await event.reply("⚠️ Пожалуйста, подождите 10 секунд перед следующим запросом Instagram.", quote=True)


@Client.on_message(filters.regex(instagram_url_pattern) & ~filters.channel, group=1)
@rate_limit(
    operation="instagram_handler",
    window_seconds=10,  # One request per 10 seconds
)
async def instagram_handler(client: Client, event: Message):
    # Extract the Instagram URL from the message
    instagram_url = re.search(instagram_url_pattern, event.text).group(0)

    # Extract the media code from the URL
    media_code = extract_instagram_code(instagram_url)

    try:
        # Get credentials from singleton
        credentials = Credentials.get_instance()
        fetcher = await InstagramMediaFetcher.create(credentials)
        media = await fetcher.get_instagram_media(media_code)
    except Exception as e:
        log.error("Error fetching Instagram media", media_code=media_code, error=str(e))
        return

    description = media.description if media.description else ""
    truncated_description = description[:200] + ("..." if len(description) > 200 else "") if description else ""
    caption_parts = ["📱 **Пост из Instagram**", f"👤 **Автор:** [{media.author_name}]({media.author_url})"]

    if truncated_description:
        caption_parts.extend(["", f"📝 {truncated_description}"])

    caption_parts.extend(["", "📊 **Статистика:**", f"❤️ {media.likes:,} лайков", f"💬 {media.comments:,} комментариев", "", f"🔗 [Открыть в Instagram]({media.source_url})"])

    caption = "\n".join(caption_parts)

    def is_video(url):
        # Check for specific video indicators in the URL
        video_indicators = ["_video_dashinit", ".mp4"]
        return any(indicator in url for indicator in video_indicators)

    if len(media.attachments) > 1:  # Multiple media items
        media_group = []
        for i, attachment in enumerate(media.attachments):
            if is_video(attachment):
                media_item = InputMediaVideo(attachment)
            else:
                media_item = InputMediaPhoto(attachment)

            if i == 0:
                media_item.caption = caption

            media_group.append(media_item)

        await event.reply_media_group(media=media_group, quote=True)
        return
    elif len(media.attachments) == 1:  # Single media item
        if is_video(media.attachments[0]):
            await event.reply_video(video=media.attachments[0], caption=caption, quote=True)
        else:
            await event.reply_photo(photo=media.attachments[0], caption=caption, quote=True)
        return
    else:
        return
