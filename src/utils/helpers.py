from io import BytesIO
from typing import Tuple, Union
from structlog import get_logger
from pyrogram.enums import ChatType
from pyrogram.types import Message

log = get_logger(__name__)

async def get_user_mention(user) -> str:
    """Get user mention"""
    return user.mention()


async def check_media_type(message: Message) -> Tuple[bool, bool, bool]:
    """
    Check if message contains photo or GIF
    Returns tuple of (has_media, is_gif, is_reply)
    """
    if message.reply_to_message and message.reply_to_message.photo:
        return True, False, True
    elif message.photo:
        return True, False, False
    elif message.reply_to_message and message.reply_to_message.animation:
        return True, True, True
    elif message.animation:
        return True, True, False
    return False, False, False


async def get_photo(message: Message) -> Union[Tuple[BytesIO, bool], Tuple[None, None]]:
    has_media, is_gif, is_reply = await check_media_type(message)

    if not has_media:
        log.info("No photo or GIF found in the message.")
        return None, None

    if is_reply:
        log.info("Media found in reply to message.")
        photo = await message.reply_to_message.download(in_memory=True)
    else:
        log.info("Media found in message.")
        photo = await message.download(in_memory=True)

    photo.seek(0)
    return photo, is_gif


def is_private_chat(message: Message) -> bool:
    """
    Check if the message is from a private chat
    
    Args:
        message: The message to check
        
    Returns:
        bool: True if the chat is private, False otherwise
    """
    return message.chat.type == ChatType.PRIVATE