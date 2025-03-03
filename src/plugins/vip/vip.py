"""VIP status management plugin"""

from pyrogram import Client, filters
from pyrogram.types import Message
from structlog import get_logger

from src.config.framework import enable_vip, disable_vip, is_vip
from src.utils.helpers import is_developer

log = get_logger(__name__)


@Client.on_message(filters.command("set_vip"), group=1)
async def set_vip_command(client: Client, message: Message):
    """
    Set or remove VIP status for a chat
    
    Args:
        client: The Pyrogram client
        message: The message containing the command
    """
    # Check if the user is a developer
    if not is_developer(message.from_user.id):
        log.warning("Unauthorized attempt to set VIP status", user_id=message.from_user.id)
        await message.reply_text("❌ У вас нет прав для использования этой команды", quote=True)
        return
    
    # Check if a chat was mentioned
    if not message.command or len(message.command) < 2:
        await message.reply_text("❌ Пожалуйста, укажите пользователя или чат\nПример: /set_vip @username", quote=True)
        return

    # Get the chat ID from the command
    target = message.command[1]
    
    # If it's a username, try to get the chat
    if target.startswith("@"):
        username = target[1:]  # Remove the @ symbol
        try:
            chat = await client.get_chat(username)
            chat_id = chat.id
        except Exception as e:
            log.error("Error getting chat", error=str(e), username=username)
            await message.reply_text(f"❌ Не удалось найти чат {target}", quote=True)
            return
    # If it's a reply, use the replied message's chat
    elif message.reply_to_message:
        chat_id = message.reply_to_message.chat.id
    # Otherwise, use the current chat
    else:
        chat_id = message.chat.id

    # Check current VIP status
    current_status = await is_vip(chat_id)
    
    try:
        # Toggle VIP status
        if current_status:
            await disable_vip(chat_id)
            await message.reply_text(f"✅ VIP статус отключен для {target}", quote=True)
            log.info("VIP status disabled", chat_id=chat_id, by_user=message.from_user.id)
        else:
            await enable_vip(chat_id)
            await message.reply_text(f"✅ VIP статус включен для {target}", quote=True)
            log.info("VIP status enabled", chat_id=chat_id, by_user=message.from_user.id)
    except Exception as e:
        log.error("Error setting VIP status", error=str(e), chat_id=chat_id)
        await message.reply_text("❌ Произошла ошибка при изменении VIP статуса", quote=True)