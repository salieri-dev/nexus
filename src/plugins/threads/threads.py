import os
import json
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from src.services.openrouter import OpenRouter
from structlog import get_logger

log = get_logger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_schema(filename: str) -> dict:
    """Load JSON schema from file"""
    schema_path = os.path.join(CURRENT_DIR, filename)
    with open(schema_path, "r") as f:
        return json.load(f)["schema"]

@Client.on_message(filters.command(["bugurt"]), group=1)
async def create_bugurt(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Укажите тему для бугурта!\nПример: /bugurt тема")
        return
        
    input_prompt = " ".join(message.command[1:])
    if len(input_prompt) < 3:
        await message.reply("Тема слишком короткая! Минимум 3 символа.")
        return
        
    open_router = OpenRouter().client
    
    # Load system prompt and schema
    with open(os.path.join(CURRENT_DIR, "bugurt", "bugurt_system_prompt.txt"), "r") as file:
        system_prompt = file.read()
    
    schema = load_schema("bugurt/output_schema.json")
    
    reply_msg = await message.reply("⚙️ Генерирую пост...")
    completion = await open_router.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Создай бугурт-тред историю с темой '{input_prompt}'. Ответ должен быть в формате JSON как описано в инструкции."
            }
        ],
        model="anthropic/claude-3.5-sonnet:beta",
        temperature=1,
        max_tokens=5000,
        response_format={"type": "json_schema", "schema": schema}
    )
    
    completion_response = completion.choices[0].message.content
    log.info(f"AI Response: {completion_response}")
    
    # Generate image from the JSON response
    from src.plugins.threads.service import generate_bugurt_image
    
    image_bytes = generate_bugurt_image(completion_response)
    if not image_bytes:
        await message.reply("Не удалось сгенерировать бугурт")
        return
    
    await reply_msg.delete()
    # Send the image
    from io import BytesIO
    
    # Convert bytes to BytesIO object
    photo = BytesIO(image_bytes)
    photo.name = "bugurt.png"
    # Parse JSON and extract story
    response_json = json.loads(completion_response)
    story_text = response_json.get('story', '')
    
    # Format story text similar to how it's done in service.py
    # First normalize newlines to @
    story_text = story_text.replace('\n', '@')
    # Split, clean parts, and join with newline-@-newline
    parts = [p.strip() for p in story_text.split('@') if p.strip()]
    story_text = '\n@\n'.join(parts)
    
    await message.reply_photo(
        photo=photo,
        caption=story_text,
        quote=True, parse_mode=ParseMode.HTML
    )

@Client.on_message(filters.command(["greentext"]), group=1)
async def create_greentext(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Укажите тему для гринтекста!\nПример: /greentext тема")
        return
        
    input_prompt = " ".join(message.command[1:])
    if len(input_prompt) < 3:
        await message.reply("Тема слишком короткая! Минимум 3 символа.")
        return
        
    open_router = OpenRouter().client
    
    # Load system prompt and schema
    with open(os.path.join(CURRENT_DIR, "greentext", "greentext_system_prompt.txt"), "r") as file:
        system_prompt = file.read()
    
    schema = load_schema("greentext/output_schema.json")
    
    reply_msg = await message.reply("⚙️ Генерирую пост...")
    completion = await open_router.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Create a greentext story with theme '{input_prompt}'. Response must be in JSON format as described in the instructions."
            }
        ],
        model="anthropic/claude-3.5-sonnet:beta",
        temperature=1,
        max_tokens=5000,
        response_format={"type": "json_schema", "schema": schema}
    )
    
    completion_response = completion.choices[0].message.content
    log.info(f"AI Response: {completion_response}")
    
    # Generate image from the JSON response
    from src.plugins.threads.service import generate_greentext_image
    
    # Use the same image generator but with greentext template
    image_bytes = generate_greentext_image(completion_response)
    if not image_bytes:
        await message.reply("Не удалось сгенерировать гринтекст")
        return
        
    await reply_msg.delete()
    # Send the image
    from io import BytesIO
    
    # Convert bytes to BytesIO object
    photo = BytesIO(image_bytes)
    photo.name = "greentext.png"
    
    # Parse JSON and extract story
    response_json = json.loads(completion_response)
    story_text = response_json.get('story', '')
    
    await message.reply_photo(
        photo=photo,
        caption=story_text,
        quote=True,
        parse_mode=ParseMode.HTML
    )