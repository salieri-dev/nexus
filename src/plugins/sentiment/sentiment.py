"""Sentiment analysis command handler"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository
from src.plugins.help import command_handler
from src.security.rate_limiter import rate_limit
from .constants import MESSAGES
from .service import SentimentService

log = get_logger(__name__)


class SentimentWrapper:
    """Wrapper for sentiment data"""

    def __init__(self, sentiment_dict: Dict[str, Any]):
        self.positive = sentiment_dict.get("positive", 0.0)
        self.negative = sentiment_dict.get("negative", 0.0)
        self.neutral = sentiment_dict.get("neutral", 0.0)
        self.sensitive_topics = sentiment_dict.get("sensitive_topics", {})


class MessageWrapper:
    """Wrapper for message dictionaries to provide expected structure and support both dict and attribute access"""

    def __init__(self, message_dict: Dict[str, Any]):
        # Store the original dictionary
        self._data = message_dict

        # Extract user_id from the message
        if "from_user" in message_dict and "id" in message_dict["from_user"]:
            self.user_id = message_dict["from_user"]["id"]
        else:
            self.user_id = message_dict.get("user_id")

        # Extract sentiment data
        if "sentiment" in message_dict and message_dict["sentiment"]:
            self.sentiment = SentimentWrapper(message_dict["sentiment"])
        else:
            self.sentiment = None

        # For raw_data access in create_sentiment_graph
        self.raw_data = self

    def __getitem__(self, key):
        """Support dictionary-style access: msg['key']"""
        return self._data[key]

    def __contains__(self, key):
        """Support 'key in msg' checks"""
        return key in self._data

    def get(self, key, default=None):
        """Support msg.get('key', default) calls"""
        return self._data.get(key, default)


def get_message_repository():
    """Get message repository instance"""
    db_client = DatabaseClient.get_instance()
    return MessageRepository(db_client.client)


@command_handler(commands=["sentiment"], description="Анализирует настроение в чате", group="Аналитика")
@Client.on_message(filters.command(["sentiment"]), group=1)
@rate_limit(operation="sentiment_handler", window_seconds=2, on_rate_limited=lambda message: message.reply("🕒 Подождите 2 секунды перед следующим запросом!"))
async def sentiment_stats(client: Client, message: Message):
    """Handle /sentiment command to show chat sentiment statistics"""
    # Only allow in groups/supergroups
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply_text(text=MESSAGES["SENTIMENT_PRIVATE_CHAT"], quote=True)
        return

    # Get messages and analyze sentiment
    init_msg = await message.reply_text(text=MESSAGES["SENTIMENT_ANALYZING"], quote=True)

    try:
        message_repository = get_message_repository()

        # Get all messages without a limit
        raw_messages = await message_repository.get_messages_by_chat(message.chat.id, limit=None)

        log.info(f"Retrieved {len(raw_messages)} messages for sentiment analysis in chat {message.chat.id}")

        # Wrap raw message dictionaries with our wrapper class
        messages = [MessageWrapper(msg) for msg in raw_messages]

        analysis = await SentimentService.analyze_chat_sentiment(messages)

        # Create and send sentiment graph
        if messages:
            graph_bytes = await SentimentService.create_sentiment_graph(messages)
            await init_msg.delete()

            # Send graph with caption
            await message.reply_photo(photo=graph_bytes, caption=MESSAGES["SENTIMENT_GRAPH_CAPTION"], quote=True)

            # Send the full detailed analysis
            await message.reply_text(text=analysis, quote=True)
        else:
            await init_msg.delete()
            await message.reply_text(text=analysis, quote=True)
    except Exception as e:
        log.error(f"Error in sentiment analysis: {e}")
        await init_msg.edit_text("❌ Произошла ошибка при анализе настроений.")
