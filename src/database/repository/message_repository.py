from typing import Dict, List, Optional
from structlog import get_logger


log = get_logger(__name__)


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
        # Try the new structure first (chat.id)
        query = {"chat.id": chat_id}
        cursor = self.collection.find(query).limit(limit)
        messages = await cursor.to_list(length=None)

        # If no messages found, try the old structure (chat_id)
        if not messages:
            query = {"chat_id": chat_id}
            cursor = self.collection.find(query).limit(limit)
            messages = await cursor.to_list(length=None)

        return messages

    async def get_messages_by_user(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific user."""
        # Try the new structure first (from_user.id)
        query = {"from_user.id": user_id}
        cursor = self.collection.find(query).limit(limit)
        messages = await cursor.to_list(length=None)

        # If no messages found, try the old structure (user_id)
        if not messages:
            query = {"user_id": user_id}
            cursor = self.collection.find(query).limit(limit)
            messages = await cursor.to_list(length=None)

        return messages

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

    async def get_user_id_by_username(self, username: str) -> Optional[int]:
        """
        Get user_id by username from message history.

        Args:
            username: Username to search for

        Returns:
            int or None: User ID if found, None otherwise
        """
        # Find the most recent message from a user with this username
        query = {"from_user.username": username}
        message = await self.collection.find_one(query, sort=[("date", -1)])

        # Check if message exists and has from_user.id
        if message and "from_user" in message and "id" in message["from_user"]:
            return message["from_user"]["id"]

        # Fallback to user_id if from_user.id is not available
        if message and "user_id" in message:
            return message["user_id"]

        return None
