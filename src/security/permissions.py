"""Permission decorators for command handlers"""
from functools import wraps

from pyrogram.enums import ChatType
from pyrogram.types import Message

from src.plugins.peer_config.settings import get_chat_setting


def requires_setting(setting: str):
    """
    Decorator to check if a specific setting is enabled in the chat
    Args:
        setting: The setting name to check (e.g. 'nsfw', 'spy', etc.)
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(client, message: Message, *args, **kwargs):
            # Skip check for private chats
            if message.chat.type != ChatType.PRIVATE:
                # Check if setting is enabled
                if not await get_chat_setting(message.chat.id, setting):
                    return await message.reply_text(
                        f"❌ В данном чате нет прав на {setting}. Включите через /settings",
                        quote=True
                    )

            # Proceed with the handler
            return await func(client, message, *args, **kwargs)

        return wrapper

    return decorator
