"""Sentiment analysis command handler"""

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message
from structlog import get_logger

from src.plugins.help import command_handler
from src.security.rate_limiter import rate_limit
from .constants import MESSAGES
from .service import SentimentService

log = get_logger(__name__)


@command_handler(commands=["sentiment"], description="Анализирует настроение в чате", group="Аналитика")
@Client.on_message(filters.command(["sentiment"]), group=1)
@rate_limit(operation="sentiment_handler", window_seconds=2, on_rate_limited=lambda message: message.reply("🕒 Подождите 2 секунды перед следующим запросом!"))
async def sentiment_stats(client: Client, message: Message):
    """Handle /sentiment command to show chat sentiment statistics"""
    # Only allow in groups/supergroups
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply_text(text=MESSAGES["SENTIMENT_PRIVATE_CHAT"], quote=True)
        return

    # Show analyzing message
    init_msg = await message.reply_text(text=MESSAGES["SENTIMENT_ANALYZING"], quote=True)

    try:
        # Call service to analyze sentiment
        analysis, graph_bytes = await SentimentService.analyze_chat_sentiment_by_id(message.chat.id)

        # Delete the initial message
        await init_msg.delete()

        # Send results
        if graph_bytes:
            # Send graph with caption
            await message.reply_photo(photo=graph_bytes, caption=MESSAGES["SENTIMENT_GRAPH_CAPTION"], quote=True)

            # Send the full detailed analysis
            await message.reply_text(text=analysis, quote=True)
        else:
            # Just send the analysis text if no graph
            await message.reply_text(text=analysis, quote=True)

    except Exception as e:
        log.error(f"Error in sentiment analysis handler: {e}")
        await init_msg.edit_text("❌ Произошла ошибка при анализе настроений.")
