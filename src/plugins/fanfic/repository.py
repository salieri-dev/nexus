from datetime import datetime, timedelta
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

log = get_logger(__name__)


class FanficRepository:
    """Repository for managing fanfic data"""

    def __init__(self, client: AsyncIOMotorClient):
        """Initialize repository with MongoDB client"""
        self.db = client["nexus"]
        self.collection = self.db["fanfics"]

    async def create_index(self):
        """Create necessary indexes"""
        await self.collection.create_index([
            ("user_id", 1),
            ("chat_id", 1),
            ("timestamp", -1)
        ])
        await self.collection.create_index([("topic", "text")])

    async def save_fanfic(self, fanfic_data: Dict) -> str:
        """
        Save a fanfic to the database.
        
        Args:
            fanfic_data: Dictionary containing:
                - user_id: User who created the fanfic
                - chat_id: Chat where fanfic was created
                - topic: Fanfic topic
                - content: Generated fanfic content
                - timestamp: Creation time
                - model: AI model used
                - temperature: Temperature setting used
        
        Returns:
            str: ID of the created document
        """
        # Ensure timestamp is present
        if "timestamp" not in fanfic_data:
            fanfic_data["timestamp"] = datetime.utcnow()

        result = await self.collection.insert_one(fanfic_data)
        return str(result.inserted_id)

    async def get_user_fanfics(self, user_id: int, limit: int = 10) -> List[Dict]:
        """
        Get fanfics created by a specific user.
        
        Args:
            user_id: User ID to fetch fanfics for
            limit: Maximum number of fanfics to return
            
        Returns:
            List[Dict]: List of fanfic documents
        """
        cursor = self.collection.find({"user_id": user_id}) \
            .sort("timestamp", -1) \
            .limit(limit)
        return await cursor.to_list(length=None)

    async def get_chat_fanfics(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """
        Get fanfics created in a specific chat.
        
        Args:
            chat_id: Chat ID to fetch fanfics for
            limit: Maximum number of fanfics to return
            
        Returns:
            List[Dict]: List of fanfic documents
        """
        cursor = self.collection.find({"chat_id": chat_id}) \
            .sort("timestamp", -1) \
            .limit(limit)
        return await cursor.to_list(length=None)

    async def search_fanfics_by_topic(self, topic: str) -> List[Dict]:
        """
        Search fanfics by topic using text search.
        
        Args:
            topic: Topic to search for
            
        Returns:
            List[Dict]: List of matching fanfic documents
        """
        cursor = self.collection.find({"$text": {"$search": topic}}) \
            .sort("timestamp", -1)
        return await cursor.to_list(length=None)

    async def get_fanfic_by_id(self, fanfic_id: str) -> Optional[Dict]:
        """
        Get a fanfic by its ID.
        
        Args:
            fanfic_id: ID of the fanfic to retrieve
            
        Returns:
            Optional[Dict]: Fanfic document if found, None otherwise
        """
        return await self.collection.find_one({"_id": fanfic_id})

    async def delete_old_fanfics(self, days: int) -> int:
        """
        Delete fanfics older than specified days.
        
        Args:
            days: Number of days to keep fanfics for
            
        Returns:
            int: Number of deleted fanfics
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.collection.delete_many({
            "timestamp": {"$lt": cutoff}
        })
        return result.deleted_count
