import re

from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InputMediaVideo, Message
from src.plugins.instagram.instagram_service import InstagramMediaFetcher
from src.utils.credentials import Credentials

from structlog import get_logger

log = get_logger(__name__)


def extract_instagram_code(url):
    pattern = r"/([A-Za-z0-9_-]{11})/?"
    match = re.search(pattern, url)
    return match.group(1) if match else None


# New regex pattern to match Instagram URLs
instagram_url_pattern = r"https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+"


@Client.on_message(filters.regex(instagram_url_pattern) & ~filters.channel, group=1)
async def insta_handler(client: Client, event: Message):
    if not event.from_user:
        return

    # Extract the Instagram URL from the message
    instagram_url = re.search(instagram_url_pattern, event.text).group(0)

    # Extract the media code from the URL
    media_code = extract_instagram_code(instagram_url)

    # Get credentials from singleton
    credentials = Credentials.get_instance()
    fetcher = await InstagramMediaFetcher.create(credentials)
    media = await fetcher.get_instagram_media(media_code)

    # Create a pretty message with safe description handling
    description = media.description if media.description else ""
    truncated_description = description[:200] + ("..." if len(description) > 200 else "") if description else ""
    caption_parts = [
        "📱 **Пост из Instagram**",
        f"👤 **Автор:** [{media.author_name}]({media.author_url})"
    ]
    
    if truncated_description:
        caption_parts.extend(["", f"📝 {truncated_description}"])
    
    caption_parts.extend([
        "",
        "📊 **Статистика:**",
        f"❤️ {media.likes:,} лайков",
        f"💬 {media.comments:,} комментариев",
        "",
        f"🔗 [Открыть в Instagram]({media.source_url})"
    ])
    
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
