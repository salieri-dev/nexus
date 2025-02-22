from pyrogram import Client, filters
from datetime import datetime
from typing import Dict, Optional
import structlog
import json

from src.database.message_repository import MessageRepository
from src.database.client import DatabaseClient


def serialize(obj):
    """Serialize objects to JSON."""
    obj = str(obj)
    obj = json.loads(obj)
    return obj

# Get the shared logger instance
logger = structlog.get_logger()

@Client.on_message(filters.all, group=0)
async def message(client: Client, message):
    """Log all incoming messages to the database."""
    try:
        # Initialize DatabaseClient using the connection from Pyrogram client
        db_client = DatabaseClient()
        db_client.client = client.mongodb["connection"]
        db_client.db = db_client.client["nexus"]  # Use the same database name as in main.py
        
        message_repo = MessageRepository(db_client)
        await message_repo.log_message(serialize(message))
        
        logger.info("Message logged successfully",
                   message_id=message.id,
                   chat_id=message.chat.id,
                   message_type=type(message).__name__)

    except Exception as e:
        logger.error("Error logging message",
                    error=str(e),
                    message_id=message.id if message else None)