import os
from datetime import datetime
from io import BytesIO
from typing import Callable, Optional, Type

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.plugins.help import command_handler
from src.security.rate_limiter import rate_limit
from src.services.openrouter import OpenRouter
from .models import BugurtResponse, GreentextResponse, ThreadResponse
from .repository import ThreadsRepository
from .service import generate_bugurt_image, generate_greentext_image

log = get_logger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def format_story_text(text: str, command: str) -> str:
    """Format story text based on command type"""
    if command == "bugurt":
        # Bugurt style with @ separators
        text = text.replace('\n', '@')
        parts = [p.strip() for p in text.split('@') if p.strip()]
        return '\n@\n'.join(parts)
    else:
        # Greentext style - just preserve newlines
        return text


async def handle_thread_generation(
        message: Message,
        command: str,
        system_prompt_path: str,
        response_model: Type[ThreadResponse],
        image_generator: Callable[[ThreadResponse], Optional[bytes]],
        error_message: str,
        prompt_language: str = "ru"
) -> None:
    """Generic handler for thread generation commands"""
    try:
        # Get database instance and initialize repositories
        db = DatabaseClient.get_instance()
        repository = ThreadsRepository(db.client)
        config_repository = BotConfigRepository(db_client=db)

        # Validate input
        if len(message.command) < 2:
            await message.reply(
                "Укажите тему!" if prompt_language == "ru" else "Specify the theme!",
                quote=True
            )
            return

        input_prompt = " ".join(message.command[1:])
        if len(input_prompt) < 3:
            await message.reply(
                "Тема слишком короткая! Минимум 3 символа." if prompt_language == "ru"
                else "Theme too short! Minimum 3 characters.",
                quote=True
            )
            return

        # Load system prompt from config
        if command == "bugurt":
            system_prompt = await config_repository.get_plugin_config_value("threads", "BUGURT_SYSTEM_PROMPT", "")
        elif command == "greentext":
            system_prompt = await config_repository.get_plugin_config_value("threads", "GREENTEXT_SYSTEM_PROMPT", "")
        else:
            # Fallback to file if command is not recognized
            with open(os.path.join(CURRENT_DIR, system_prompt_path), "r") as file:
                system_prompt = file.read()

        # Generate AI response
        reply_msg = await message.reply("⚙️ Генерирую пост..." if prompt_language == "ru" else "⚙️ Generating post...",
                                        quote=True)
        try:
            openrouter = OpenRouter()

            # Get model name from config
            model_name = "anthropic/claude-3.5-sonnet:beta"  # Default
            if command == "bugurt":
                model_name = await config_repository.get_plugin_config_value("threads", "BUGURT_MODEL_NAME",
                                                                             "anthropic/claude-3.5-sonnet:beta")
            elif command == "greentext":
                model_name = await config_repository.get_plugin_config_value("threads", "GREENTEXT_MODEL_NAME",
                                                                             "anthropic/claude-3.5-sonnet:beta")

            completion = await openrouter.client.beta.chat.completions.parse(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": (
                                       f"Создай {command}-тред историю с темой '{input_prompt}'" if prompt_language == "ru"
                                       else f"Create a {command} story with theme '{input_prompt}'"
                                   ) + ". Response must be in JSON format as described in the instructions."
                    }
                ],
                model=model_name,
                temperature=1,
                max_tokens=5000,
                response_format=response_model
            )

            thread_response = completion.choices[0].message.parsed
            log.info(f"AI Response: {completion}")

            # Generate image
            image_bytes = image_generator(thread_response)
            if not image_bytes:
                await message.reply(error_message, quote=True)
                return

            # Store thread data
            thread_data = {
                "user_id": message.from_user.id,
                "chat_id": message.chat.id,
                "command": command,
                "theme": input_prompt,
                "story": thread_response.story,
                "comments": thread_response.comments,
                "timestamp": datetime.utcnow(),
                "model": model_name,
                "temperature": 1,
                "language": "ru" if command == "bugurt" else "en"
            }
            await repository.save_thread(thread_data)

            # Format story text for display
            formatted_story = format_story_text(thread_response.story, command)

            # Send result
            await reply_msg.delete()
            photo = BytesIO(image_bytes)
            photo.name = f"{command}.png"
            await message.reply_photo(
                photo=photo,
                caption=formatted_story,
                quote=True,
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            log.error(f"Failed to generate {command}: {e}")
            await message.reply(
                f"Произошла ошибка при генерации {command}а" if prompt_language == "ru"
                else f"An error occurred while generating {command}",
                quote=True
            )
            if reply_msg:
                await reply_msg.delete()

    except Exception as e:
        log.error(f"Database error in {command} command", error=str(e))
        await message.reply(
            "Произошла ошибка при работе с базой данных" if prompt_language == "ru"
            else "A database error occurred",
            quote=True
        )


@Client.on_message(filters.command(["bugurt"]), group=1)
@command_handler(commands=["bugurt"], arguments="[тема]", description="Создать бугурт", group="Мемы")
@rate_limit(
    operation="bugurt_handler",
    window_seconds=30,  # One request per 45 seconds
    on_rate_limited=lambda message: message.reply("🕒 Подождите 30 секунд перед следующим запросом!")
)
async def create_bugurt(client: Client, message: Message):
    """Handler for /bugurt command"""
    await handle_thread_generation(
        message=message,
        command="bugurt",
        system_prompt_path="bugurt/bugurt_system_prompt.txt",
        response_model=BugurtResponse,
        image_generator=generate_bugurt_image,
        error_message="Не удалось сгенерировать бугурт",
        prompt_language="ru"
    )


@Client.on_message(filters.command(["greentext"]), group=1)
@command_handler(commands=["greentext"], arguments="[тема]", description="Создать гринтекст", group="Мемы")
@rate_limit(
    operation="greentext_handler",
    window_seconds=30,  # One request per 45 seconds
    on_rate_limited=lambda message: message.reply("🕒 Подождите 30 секунд перед следующим запросом!")
)
async def create_greentext(client: Client, message: Message):
    """Handler for /greentext command"""
    await handle_thread_generation(
        message=message,
        command="greentext",
        system_prompt_path="greentext/greentext_system_prompt.txt",
        response_model=GreentextResponse,
        image_generator=generate_greentext_image,
        error_message="Failed to generate greentext",
        prompt_language="en"
    )
