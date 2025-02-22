from pyrogram import Client, filters
import structlog
import json

from src.plugins.spy.message_repository import MessageRepository
from src.database.client import DatabaseClient

# Get the shared logger instance
logger = structlog.get_logger()

def serialize(obj: str) -> dict:
    """Serialize objects to JSON with caching."""
    return json.loads(str(obj))

def get_user_identifier(message) -> str:
    """Extract user identifier from message."""
    user = message.from_user
    return user.username or user.first_name or user.last_name or "Unknown User"

def get_message_content(message) -> str:
    """Extract and format message content."""
    content = message.text or message.caption or "None"
    content = content.replace('\n', ' ').strip()
    
    if message.media:
        media_type = str(message.media).replace("MessageMediaType.", "")
        content += f" [{media_type}]"
    
    return content

@Client.on_message(filters.all, group=0)
async def message(client: Client, message):
    """Log all incoming messages to the database."""
    try:
        # Initialize DatabaseClient using the connection from Pyrogram client
        db_client = DatabaseClient()
        db_client.client = client.mongodb["connection"]
        db_client.db = db_client.client["nexus"]
        
        # Log message to database
        message_repo = MessageRepository(db_client)
        await message_repo.log_message(serialize(message))
        
        # Build logging data
        user_identifier = get_user_identifier(message)
        msg_content = get_message_content(message)
        chat_title = "DM" if message.chat.type == "private" else message.chat.title

        logger.info(
            f"[{chat_title}] [{message.chat.id}] [{user_identifier}] [{message.from_user.id}]: {msg_content}",
            message_id=message.id,
            chat_id=message.chat.id, 
            message_type=type(message).__name__
        )

    except Exception as e:
        logger.error(
            "Error logging message",
            error=str(e),
            message_id=getattr(message, 'id', None)
        )