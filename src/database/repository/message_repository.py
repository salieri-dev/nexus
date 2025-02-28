from datetime import datetime
from typing import Dict, List, Optional, Any
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
        
    async def find_messages_by_query(self, query: Dict, limit: Optional[int] = None) -> List[Dict]:
        """
        Find messages by custom query.
        
        Args:
            query: MongoDB query dictionary
            limit: Maximum number of messages to return (None for no limit)
            
        Returns:
            List of messages matching the query
        """
        cursor = self.collection.find(query)
        if limit is not None:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=None)
        
    async def get_messages_by_date_range(self, start_date: datetime, end_date: datetime,
                                         chat_id: int, exclude_commands: bool = True,
                                         exclude_bots: bool = True) -> List[Dict]:
        """
        Get messages within a specific date range for a chat.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (exclusive)
            chat_id: Chat ID to filter by
            exclude_commands: Whether to exclude command messages
            exclude_bots: Whether to exclude bot messages
            
        Returns:
            List of messages matching the criteria
        """
        query = {
            "created_at": {"$gte": start_date, "$lt": end_date},
            "chat.id": chat_id
        }
        
        # Add filters for commands and bots if needed
        if exclude_commands or exclude_bots:
            and_conditions = []
            
            if exclude_commands:
                and_conditions.append({
                    "$or": [
                        {"text": {"$exists": True, "$ne": "", "$not": {"$regex": "^/"}}},
                        {"caption": {"$exists": True, "$ne": ""}}
                    ]
                })
                
            if exclude_bots:
                and_conditions.append({
                    "$or": [
                        {"from_user.is_bot": False},
                        {"from_user.is_bot": {"$exists": False}}
                    ]
                })
                
            if and_conditions:
                query["$and"] = and_conditions
        
        cursor = self.collection.find(query).sort("created_at", 1)
        return await cursor.to_list(length=None)
        
    async def aggregate_messages(self, pipeline: List[Dict]) -> List[Dict]:
        """
        Perform an aggregation on the messages collection.
        
        Args:
            pipeline: MongoDB aggregation pipeline
            
        Returns:
            List of documents resulting from the aggregation
        """
        cursor = self.collection.aggregate(pipeline)
        return await cursor.to_list(length=None)
        
    async def find_one_message_by_chat_id(self, chat_id: int) -> Optional[Dict]:
        """
        Find a single message from a specific chat.
        
        Args:
            chat_id: Chat ID to filter by
            
        Returns:
            A message from the chat or None if not found
        """
        query = {"chat.id": chat_id}
        return await self.collection.find_one(query)
