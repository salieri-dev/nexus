from datetime import datetime
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from structlog import get_logger
from src.database.client import DatabaseClient
from .repository import FanficRepository
from .service import generate_fanfic

log = get_logger(__name__)


@Client.on_message(filters.command(["fanfic"]), group=1)
async def fanfic_handler(client: Client, message: Message):
    """Handler for /fanfic command"""
    try:
        # Get database instance and initialize repository
        db = DatabaseClient.get_instance()
        repository = FanficRepository(db.client)
        
        # Validate input
        if len(message.command) < 2:
            await message.reply("❌ Пожалуйста, укажите тему для фанфика после команды /fanfic", quote=True)
            return
            
        # Get the topic from the command
        topic = " ".join(message.command[1:])
        if len(topic) < 3:
            await message.reply("❌ Тема слишком короткая! Минимум 3 символа.", quote=True)
            return
            
        # Send initial response
        reply_msg = await message.reply("⚙️ Генерирую фанфик...", quote=True)
        
        try:
            # Generate fanfic using Pydantic model
            fanfic_response = await generate_fanfic(topic)
            
            if not fanfic_response:
                await reply_msg.edit_text("❌ Не удалось сгенерировать фанфик. Попробуйте позже.")
                return
                
            # Extract title and content from Pydantic model
            title = fanfic_response.title
            content = fanfic_response.content
            
            # Format the response
            formatted_response = f"<b>{title}</b>\n\n{content}"
            
            # Store fanfic data in database
            fanfic_record = {
                "user_id": message.from_user.id,
                "chat_id": message.chat.id,
                "topic": topic,
                "title": title,
                "content": content,
                "timestamp": datetime.utcnow(),
                "model": "x-ai/grok-2-1212",
                "temperature": 0.8
            }
            await repository.save_fanfic(fanfic_record)
            
            # Send the result
            await reply_msg.delete()
            
            # Split message if it's too long
            if len(formatted_response) > 4000:
                # Send title and first part
                first_part = formatted_response[:4000]
                await message.reply(first_part, quote=True, parse_mode=ParseMode.HTML)
                
                # Send remaining parts
                remaining = formatted_response[4000:]
                await message.reply(remaining, quote=True, parse_mode=ParseMode.HTML)
            else:
                await message.reply(formatted_response, quote=True, parse_mode=ParseMode.HTML)
                
        except Exception as e:
            log.error(f"Error generating fanfic: {e}")
            await reply_msg.edit_text("❌ Произошла ошибка при генерации фанфика.")
            
    except Exception as e:
        log.error(f"Database error in fanfic command", error=str(e))
        await message.reply("❌ Произошла ошибка при работе с базой данных", quote=True)
