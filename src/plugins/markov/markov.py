"""Markov chain text generation plugin"""

import re
from typing import Optional, List, Tuple

import markovify
from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository
from src.plugins.help import command_handler
from src.security.rate_limiter import rate_limit
from src.utils.helpers import is_private_chat

log = get_logger(__name__)
MIN_MESSAGES = 10


class MarkovTextGenerator:
    def __init__(self, message_repository):
        self.message_repository = message_repository

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean text for Markov chain generation"""
        patterns = [
            (r"https?://\S+", ""),  # Remove URLs
            (r"/\w+@\w+", ""),  # Remove command mentions
            (r"/\w+", ""),  # Remove commands
            (r"\s+", " "),  # Normalize whitespace
        ]
        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text)
        return text.strip()

    async def get_messages(self, chat_id: int, user_id: Optional[int] = None, username: Optional[str] = None) -> List[dict]:
        """Get messages from database based on filters"""
        queries = []
        if user_id:
            queries = [{"chat.id": chat_id, "from_user.id": user_id}, {"chat_id": chat_id, "user_id": user_id}]
        elif username:
            queries = [{"chat.id": chat_id, "from_user.username": username}, {"chat_id": chat_id, "username": username}]
        else:
            queries = [
                {"chat.id": chat_id},
                None,  # Will use get_messages_by_chat as fallback
            ]

        for query in queries:
            if query is None:
                messages = await self.message_repository.get_messages_by_chat(chat_id)
            else:
                messages = await self.message_repository.find_messages_by_query(query)

            if messages and len(messages) >= MIN_MESSAGES:
                return messages
        return []

    def extract_texts(self, messages: List[dict]) -> List[str]:
        """Extract and clean texts from messages"""
        texts = []
        for msg in messages:
            text = msg.get("text") or msg.get("caption")
            if text:
                cleaned = self.clean_text(text)
                if cleaned:
                    texts.append(cleaned)
        return texts

    async def build_model(self, chat_id: int, user_id: Optional[int] = None, username: Optional[str] = None) -> Optional[markovify.Text]:
        """Build a Markov chain model from messages"""
        try:
            messages = await self.get_messages(chat_id, user_id, username)
            if not messages:
                return None

            texts = self.extract_texts(messages)
            if not texts:
                return None

            combined_text = "\n".join(texts)
            return markovify.Text(combined_text, state_size=2)
        except Exception as e:
            log.error(f"Error building Markov model: {e}")
            return None


async def get_mentioned_user(message: Message, message_repository) -> Optional[Tuple[int, str]]:
    """Get the first mentioned user from message"""
    if message.reply_to_message and message.reply_to_message.from_user:
        return (message.reply_to_message.from_user.id, message.reply_to_message.from_user.username)

    if message.entities:
        for entity in message.entities:
            if entity.type == MessageEntityType.MENTION:
                username = message.text[entity.offset + 1 : entity.offset + entity.length]
                user_id = await message_repository.get_user_id_by_username(username)
                return (user_id, username)
    return None


async def generate_text(model: markovify.Text) -> Optional[str]:
    """Generate text using the Markov model"""
    return model.make_sentence(tries=100) or model.make_short_sentence(140, tries=100)


@command_handler(commands=["markov"], description="Генерирует текст на основе сообщений в чате", group="сглыпа")
@Client.on_message(filters.command("markov"), group=2)
@rate_limit(operation="markov_handler", window_seconds=2, on_rate_limited=lambda message: message.reply("🕒 Подождите 2 секунды перед следующим запросом!"))
async def markov_command(client: Client, message: Message):
    """Generate text using a Markov chain based on chat messages"""
    if is_private_chat(message):
        await message.reply_text("⚠️ Команда не поддерживается в личных сообщениях.", quote=True)
        return

    notification = await message.reply_text("🔄 Генерирую текст...", quote=True)
    try:
        message_repository = MessageRepository(DatabaseClient.get_instance().client)
        generator = MarkovTextGenerator(message_repository)
        model = await generator.build_model(message.chat.id)

        if not model:
            await notification.edit_text("⚠️ Недостаточно сообщений для генерации текста.")
            return

        text = await generate_text(model)
        await notification.edit_text(f"🤖 {text}" if text else "⚠️ Не удалось сгенерировать текст.")
    except Exception as e:
        log.error(f"Error in markov command: {e}")
        await notification.edit_text("❌ Произошла ошибка при генерации текста.")


@command_handler(commands=["impersonate"], description="Пародирует человека", group="сглыпа")
@Client.on_message(filters.command("impersonate"), group=2)
@rate_limit(operation="markov_handler", window_seconds=2, on_rate_limited=lambda message: message.reply("🕒 Подождите 2 секунды перед следующим запросом!"))
async def impersonate_command(client: Client, message: Message):
    """Generate user-specific text"""
    if is_private_chat(message):
        await message.reply_text("⚠️ Команда не поддерживается в личных сообщениях.", quote=True)
        return

    notification = await message.reply_text("🔄 Генерирую пародию...", quote=True)
    try:
        message_repository = MessageRepository(DatabaseClient.get_instance().client)
        user_info = await get_mentioned_user(message, message_repository)

        if not user_info:
            await notification.edit_text("⚠️ Укажите пользователя через @упоминание или ответьте на его сообщение.")
            return

        user_id, username = user_info
        generator = MarkovTextGenerator(message_repository)
        model = await generator.build_model(message.chat.id, user_id, username)

        if not model:
            await notification.edit_text(f"⚠️ Недостаточно сообщений от {'@' + username if username else 'пользователя'} для генерации пародии.")
            return

        text = await generate_text(model)
        user_mention = f"@{username}" if username else f"пользователя {user_id}"
        response = f"🎭 Пародия на {user_mention}:\n\n{text}" if text else f"⚠️ Не удалось сгенерировать пародию на {user_mention}."
        await notification.edit_text(response)
    except Exception as e:
        log.error(f"Error in impersonate command: {e}")
        await notification.edit_text("❌ Произошла ошибка при генерации пародии.")
