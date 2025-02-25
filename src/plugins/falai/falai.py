import os

from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.plugins.settings.settings import get_chat_setting
from .service import transcribe_audio

log = get_logger(__name__)

# Constants
MAX_AUDIO_DURATION = 600  # 10 minutes
TRANSCRIPTION_SUCCESS = "\n> {}"  # Added newline and space after >
TRANSCRIPTION_ERROR = "❌ Не удалось транскрибировать аудио"

from src.security.ratelimiter.rate_limiter import rate_limit


@Client.on_message(filters.voice | filters.audio | filters.video_note, group=1)  # Changed to group 1 to run earlier
@rate_limit(operation="transcribe", window_seconds=20)
async def transcribe_handler(client: Client, message: Message):
    """Handle voice and audio messages for transcription"""
    if not message.from_user:
        return

    # Skip transcription in non-private chats if disabled
    if message.chat.type != ChatType.PRIVATE:
        if not await get_chat_setting(message.chat.id, 'transcribe'):
            return

    # Get audio duration
    duration = (
        message.audio.duration if message.audio
        else message.voice.duration if message.voice
        else message.video_note.duration if message.video_note
        else None
    )

    if duration and duration > MAX_AUDIO_DURATION:
        log.info("Audio too long")
        return

    log.info(
        "Processing audio message",
        chat_id=message.chat.id,
        duration=duration
    )

    # Download the audio file
    file_path = await message.download()
    if not file_path:
        log.error("Could not download audio file")
        await message.reply_text(TRANSCRIPTION_ERROR, quote=True)
        return

    # Transcribe the audio
    result = await transcribe_audio(file_path)

    # Clean up downloaded file
    os.remove(file_path)

    # Skip if transcription contains blocked text
    blocked_texts = [
        "DimaTorzok",
        "Продолжение следует"
    ]

    if any(text in result["transcription"] for text in blocked_texts):
        log.info("Skipping transcription containing blocked text")
        return

    # Only reply if transcription was successful
    if result["transcription"]:
        await message.reply_text(
            TRANSCRIPTION_SUCCESS.format(result["transcription"]),
            quote=True,
            parse_mode=ParseMode.DEFAULT
        )
