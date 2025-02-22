from typing import Dict, List, Optional
from datetime import datetime
from src.database.client import DatabaseClient

class MessageRepository:
    """Repository for handling message-related database operations."""
    
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client
        self.collection = "messages"

    async def log_message(self, message_data: Dict) -> str:
        """
        Log a message to the database.
        
        Args:
            message_data: Dictionary containing message information
        
        Returns:
            str: ID of the inserted document
        """
        return await self.db.insert_one(self.collection, message_data)

    async def get_messages_by_chat(self, chat_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific chat."""
        query = {"chat_id": chat_id}
        return await self.db.find_many(self.collection, query)

    async def get_messages_by_user(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific user."""
        query = {"user_id": user_id}
        return await self.db.find_many(self.collection, query)

    async def get_message_by_id(self, message_id: int) -> Optional[Dict]:
        """Get a specific message by its ID."""
        query = {"message_id": message_id}
        return await self.db.find_one(self.collection, query)

    async def delete_messages_by_chat(self, chat_id: int) -> int:
        """Delete all messages from a specific chat."""
        query = {"chat_id": chat_id}
        return await self.db.delete_many(self.collection, query)

    async def get_message_count_by_chat(self, chat_id: int) -> int:
        """Get the total number of messages in a chat."""
        query = {"chat_id": chat_id}
        return await self.db.count_documents(self.collection, query)

    async def get_message_count_by_user(self, user_id: int) -> int:
        """Get the total number of messages by a user."""
        query = {"user_id": user_id}
        return await self.db.count_documents(self.collection, query)