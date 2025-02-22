from typing import Dict, List, Optional
from src.database.client import DatabaseClient


class MessageRepository:
    """Repository for handling message-related database operations."""

    def __init__(self, db):
        self.db = db["nexus"]
        self.collection = self.db["messages"]

    async def insert_message(self, message_data: Dict) -> str:
        """
        Log a message to the database.
        
        Args:
            message_data: Dictionary containing message information
        
        Returns:
            str: ID of the inserted document
        """
        result = await self.collection.insert_one(message_data)
        return str(result.inserted_id)

    async def get_messages_by_chat(self, chat_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific chat."""
        query = {"chat_id": chat_id}
        cursor = self.collection.find(query).limit(limit)
        return await cursor.to_list(length=None)

    async def get_messages_by_user(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific user."""
        query = {"user_id": user_id}
        cursor = self.collection.find(query).limit(limit)
        return await cursor.to_list(length=None)

    async def get_message_by_id(self, message_id: int) -> Optional[Dict]:
        """Get a specific message by its ID."""
        query = {"message_id": message_id}
        return await self.collection.find_one(query)

    async def delete_messages_by_chat(self, chat_id: int) -> int:
        """Delete all messages from a specific chat."""
        query = {"chat_id": chat_id}
        result = await self.collection.delete_many(query)
        return result.deleted_count

    async def get_message_count_by_chat(self, chat_id: int) -> int:
        """Get the total number of messages in a chat."""
        query = {"chat_id": chat_id}
        return await self.collection.count_documents(query)

    async def get_message_count_by_user(self, user_id: int) -> int:
        """Get the total number of messages by a user."""
        query = {"user_id": user_id}
        return await self.collection.count_documents(query)
