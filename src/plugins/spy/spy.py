import json
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.message_repository import MessageRepository

# Get the shared logger instance
log = get_logger(__name__)


def serialize(obj: str) -> dict:
    """Serialize objects to JSON with caching."""
    return json.loads(str(obj))


def get_user_identifier(message) -> str:
    """Extract user identifier from message."""
    if message.from_user is None:
        # Handle channel posts or messages without a user
        return "Channel" if message.chat.type == ChatType.CHANNEL else "Unknown"

    user = message.from_user
    return user.username or user.first_name or user.last_name or "Unknown User"


def get_message_content(message) -> str:
    """Extract and format message content."""
    content = message.text or message.caption or "None"
    content = content.replace("\n", " ").strip()

    if message.media:
        media_type = str(message.media).replace("MessageMediaType.", "")
        content += f" [{media_type}]"

    if message.service:
        message_service = str(message.service).replace("MessageServiceType.", "")
        content += f" [{message_service}]"

    return content


@Client.on_message(filters.all, group=0)
async def message(client: Client, message):
    """Log all incoming messages to the database."""
    try:
        # Use shared database instance
        db_client = DatabaseClient.get_instance()

        # Initialize repositories
        message_repo = MessageRepository(db_client.client)

        # Prepare message data with created_at
        message_data = serialize(message)
        message_data["created_at"] = datetime.now(timezone.utc)

        # Store message
        await message_repo.insert_message(message_data)

        # Build logging data
        user_identifier = get_user_identifier(message)
        msg_content = get_message_content(message)
        chat_title = "DM" if message.chat.type == ChatType.PRIVATE else message.chat.title

        log.info(f"[{chat_title}] [{message.chat.id}] [{user_identifier}] [{message.from_user.id if message.from_user else 'N/A'}]: {msg_content}", message_id=message.id, chat_id=message.chat.id, message_type=type(message).__name__)

    except Exception as e:
        log.error("Error logging message", error=str(e), message_id=getattr(message, "id", None))
