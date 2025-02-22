import os
import json
from typing import Callable, Optional
from io import BytesIO
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from src.services.openrouter import OpenRouter
from src.database.client import DatabaseClient
from structlog import get_logger

from .service import generate_bugurt_image, generate_greentext_image
from .repository import ThreadsRepository

log = get_logger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_schema(filename: str) -> dict:
    """Load JSON schema from file"""
    schema_path = os.path.join(CURRENT_DIR, filename)
    with open(schema_path, "r") as f:
        return json.load(f)["schema"]

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
    schema_path: str,
    image_generator: Callable[[str], Optional[bytes]],
    error_message: str,
    prompt_language: str = "ru"
) -> None:
    """Generic handler for thread generation commands"""
    try:
        # Get database instance and initialize repository
        db = DatabaseClient.get_instance()
        repository = ThreadsRepository(db.client)

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

        # Load system prompt and schema
        with open(os.path.join(CURRENT_DIR, system_prompt_path), "r") as file:
            system_prompt = file.read()
        schema = load_schema(schema_path)

        # Generate AI response
        reply_msg = await message.reply("⚙️ Генерирую пост..." if prompt_language == "ru" else "⚙️ Generating post...", quote=True)
        try:
            open_router = OpenRouter().client
            completion = await open_router.chat.completions.create(
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
                model="anthropic/claude-3.5-sonnet:beta",
                temperature=1,
                max_tokens=5000,
                response_format={"type": "json_schema", "schema": schema}
            )
            
            completion_response = completion.choices[0].message.content
            log.info(f"AI Response: {completion_response}")

            # Generate image
            image_bytes = image_generator(completion_response)
            if not image_bytes:
                await message.reply(error_message, quote=True)
                return

            # Parse JSON for caption and storage
            response_json = json.loads(completion_response)
            story_text = response_json.get('story', '')
            comments = response_json.get('2ch_comments' if command == 'bugurt' else '4ch_comments', [])
            
            # Store thread data
            thread_data = {
                "user_id": message.from_user.id,
                "chat_id": message.chat.id,
                "command": command,
                "theme": input_prompt,
                "story": story_text,
                "comments": comments,
                "timestamp": datetime.utcnow(),
                "model": "anthropic/claude-3.5-sonnet:beta",
                "temperature": 1,
                "language": "ru" if command == "bugurt" else "en"
            }
            await repository.save_thread(thread_data)
            
            # Format story text for display
            formatted_story = format_story_text(story_text, command)

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
async def create_bugurt(client: Client, message: Message):
    """Handler for /bugurt command"""
    await handle_thread_generation(
        message=message,
        command="bugurt",
        system_prompt_path="bugurt/bugurt_system_prompt.txt",
        schema_path="bugurt/output_schema.json",
        image_generator=generate_bugurt_image,
        error_message="Не удалось сгенерировать бугурт",
        prompt_language="ru"
    )

@Client.on_message(filters.command(["greentext"]), group=1)
async def create_greentext(client: Client, message: Message):
    """Handler for /greentext command"""
    await handle_thread_generation(
        message=message,
        command="greentext",
        system_prompt_path="greentext/greentext_system_prompt.txt",
        schema_path="greentext/output_schema.json",
        image_generator=generate_greentext_image,
        error_message="Failed to generate greentext",
        prompt_language="en"
    )
