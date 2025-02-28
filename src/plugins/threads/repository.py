from datetime import datetime, timedelta
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

log = get_logger(__name__)


class ThreadsRepository:
    """Repository for managing thread data"""

    def __init__(self, client: AsyncIOMotorClient):
        """Initialize repository with MongoDB client"""
        self.db = client["nexus"]
        self.collection = self.db["threads"]

    async def create_index(self):
        """Create necessary indexes"""
        await self.collection.create_index([("user_id", 1), ("chat_id", 1), ("timestamp", -1)])
        await self.collection.create_index([("command", 1)])
        await self.collection.create_index([("theme", "text")])

    async def save_thread(self, thread_data: Dict) -> str:
        """
        Save a thread to the database.

        Args:
            thread_data: Dictionary containing:
                - user_id: User who created the thread
                - chat_id: Chat where thread was created
                - command: Type of thread (bugurt/greentext)
                - theme: Thread theme
                - story: Generated story
                - comments: List of generated comments
                - image_hash: Hash of generated image
                - timestamp: Creation time

        Returns:
            str: ID of the created document
        """
        # Ensure timestamp is present
        if "timestamp" not in thread_data:
            thread_data["timestamp"] = datetime.utcnow()

        result = await self.collection.insert_one(thread_data)
        return str(result.inserted_id)

    async def get_user_threads(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Get threads created by a specific user.

        Args:
            user_id: User ID to fetch threads for
            limit: Maximum number of threads to return

        Returns:
            List[Dict]: List of thread documents
        """
        cursor = self.collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def get_chat_threads(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """
        Get threads created in a specific chat.

        Args:
            chat_id: Chat ID to fetch threads for
            limit: Maximum number of threads to return

        Returns:
            List[Dict]: List of thread documents
        """
        cursor = self.collection.find({"chat_id": chat_id}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def search_threads_by_theme(self, theme: str) -> List[Dict]:
        """
        Search threads by theme using text search.

        Args:
            theme: Theme to search for

        Returns:
            List[Dict]: List of matching thread documents
        """
        cursor = self.collection.find({"$text": {"$search": theme}}).sort("timestamp", -1)
        return await cursor.to_list(length=None)

    async def get_thread_by_id(self, thread_id: str) -> Optional[Dict]:
        """
        Get a thread by its ID.

        Args:
            thread_id: ID of the thread to retrieve

        Returns:
            Optional[Dict]: Thread document if found, None otherwise
        """
        return await self.collection.find_one({"_id": thread_id})

    async def get_threads_by_command(self, command: str, limit: int = 10) -> List[Dict]:
        """
        Get threads of a specific type.

        Args:
            command: Thread type (bugurt/greentext)
            limit: Maximum number of threads to return

        Returns:
            List[Dict]: List of thread documents
        """
        cursor = self.collection.find({"command": command}).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=None)

    async def get_user_command_stats(self, user_id: int) -> Dict[str, int]:
        """
        Get statistics of thread types created by a user.

        Args:
            user_id: User ID to get stats for

        Returns:
            Dict[str, int]: Count of each thread type
        """
        pipeline = [{"$match": {"user_id": user_id}}, {"$group": {"_id": "$command", "count": {"$sum": 1}}}]
        cursor = self.collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return {doc["_id"]: doc["count"] for doc in results}

    async def delete_old_threads(self, days: int) -> int:
        """
        Delete threads older than specified days.

        Args:
            days: Number of days to keep threads for

        Returns:
            int: Number of deleted threads
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.collection.delete_many({"timestamp": {"$lt": cutoff}})
        return result.deleted_count
