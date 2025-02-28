from datetime import datetime
from typing import Optional, Dict, Tuple

from pydantic import BaseModel, Field
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.services.openrouter import OpenRouter
from .constants import DEFAULT_TEMPERATURE, MAX_TOKENS, MAX_MESSAGE_LENGTH, MESSAGES
from .repository import FanficRepository

log = get_logger(__name__)


# Pydantic model for fanfic response
class FanficResponse(BaseModel):
    """Pydantic model for fanfic response"""

    title: str = Field(description="The title of the fanfiction")
    content: str = Field(description="The full text of the fanfiction")


class FanficService:
    """Service for fanfic generation and management"""

    @staticmethod
    def get_repository():
        """Get fanfic repository instance"""
        db_client = DatabaseClient.get_instance()
        return FanficRepository(db_client.client)

    @staticmethod
    def get_config_repository():
        """Get bot config repository instance"""
        db_client = DatabaseClient.get_instance()
        return BotConfigRepository(db_client)

    @staticmethod
    async def validate_topic(topic: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the fanfic topic.

        Args:
            topic: The topic to validate

        Returns:
            Tuple containing:
            - Boolean indicating if the topic is valid
            - Error message if invalid, None otherwise
        """
        if not topic:
            return False, MESSAGES["MISSING_TOPIC"]

        if len(topic) < 3:
            return False, MESSAGES["TOPIC_TOO_SHORT"]

        return True, None

    @staticmethod
    async def generate_fanfic(topic: str) -> Optional[FanficResponse]:
        """
        Generate a fanfiction based on the given topic using OpenRouter API.

        Args:
            topic: The topic/theme for the fanfiction

        Returns:
            Optional[FanficResponse]: Pydantic model containing the title and content of the generated fanfiction,
                                    or None if generation failed
        """
        config_repo = FanficService.get_config_repository()

        # Get system prompt and model name from config
        system_prompt = await config_repo.get_plugin_config_value("fanfic", "FANFIC_SYSTEM_PROMPT")
        model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME", "anthropic/claude-3.5-sonnet:beta")

        open_router = OpenRouter().client

        # Create the completion request using Pydantic model
        completion = await open_router.beta.chat.completions.parse(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Создай фанфик на тему '{topic}'. Это должно быть в формате JSON обязательно по схеме что тебе предоставляю я."}], model=model_name, temperature=DEFAULT_TEMPERATURE, max_tokens=MAX_TOKENS, response_format=FanficResponse
        )
        log.info(completion)

        # The response is already parsed into FanficResponse model
        fanfic_response = completion.choices[0].message.parsed
        return fanfic_response

    @staticmethod
    async def save_fanfic_to_db(topic: str, fanfic_response: FanficResponse, user_id: int, chat_id: int) -> str:
        """
        Save generated fanfic to the database.

        Args:
            topic: The topic of the fanfic
            fanfic_response: The generated fanfic response
            user_id: ID of the user who requested the fanfic
            chat_id: ID of the chat where the fanfic was requested

        Returns:
            str: ID of the saved fanfic record
        """
        repository = FanficService.get_repository()
        config_repo = FanficService.get_config_repository()

        # Get model name from config
        model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME", "anthropic/claude-3.5-sonnet:beta")

        # Store fanfic data in database
        fanfic_record = {"user_id": user_id, "chat_id": chat_id, "topic": topic, "title": fanfic_response.title, "content": fanfic_response.content, "timestamp": datetime.utcnow(), "model": model_name, "temperature": DEFAULT_TEMPERATURE}

        return await repository.save_fanfic(fanfic_record)

    @staticmethod
    async def format_and_send_response(message: Message, fanfic_response: FanficResponse, reply_msg: Message) -> None:
        """
        Format and send the fanfic response to the user.

        Args:
            message: Original message that triggered the fanfic generation
            fanfic_response: The generated fanfic response
            reply_msg: The initial "generating" message to be deleted
        """
        # Extract title and content from Pydantic model
        title = fanfic_response.title
        content = fanfic_response.content

        # Format the response
        formatted_response = f"<b>{title}</b>\n\n{content}"

        # Delete the initial "generating" message
        await reply_msg.delete()

        # Split message if it's too long
        if len(formatted_response) > MAX_MESSAGE_LENGTH:
            # Send title and first part
            first_part = formatted_response[:MAX_MESSAGE_LENGTH]
            await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)

            # Send remaining parts
            remaining = formatted_response[MAX_MESSAGE_LENGTH:]
            await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
        else:
            await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)
