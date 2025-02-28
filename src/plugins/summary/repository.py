"""Repository for Summary plugin data"""

from datetime import datetime
from typing import Dict, List, Optional, Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from structlog import get_logger

log = get_logger(__name__)


class SummaryRepository:
    """Repository for managing chat summaries data"""

    def __init__(self, client: AsyncIOMotorClient):
        """Initialize repository with MongoDB client"""
        self.db = client["nexus"]
        self.summaries = self.db["summaries"]

    async def create_indexes(self):
        """Create necessary indexes for efficient querying"""
        await self.summaries.create_index([("chat_id", 1)])
        await self.summaries.create_index([("generated_at", -1)])
        await self.summaries.create_index([("chat_id", 1), ("generated_at", -1)])
        log.info("Created indexes for summaries collection")

    async def store_summary(self, chat_id: int, chat_title: str, summary_date: datetime, themes: List[Dict], message_count: int) -> str:
        """
        Store a generated summary in the database.

        Args:
            chat_id: ID of the chat the summary is for
            chat_title: Title of the chat
            summary_date: Date the summary is for
            themes: List of themes extracted from the chat
            message_count: Number of messages analyzed for this summary

        Returns:
            str: ID of the inserted document
        """
        summary_doc = {"chat_id": chat_id, "chat_title": chat_title, "summary_date": summary_date, "generated_at": datetime.utcnow(), "themes": themes, "message_count": message_count}

        result = await self.summaries.insert_one(summary_doc)
        log.info("Stored summary", chat_id=chat_id, summary_date=summary_date.strftime("%Y-%m-%d"), summary_id=str(result.inserted_id))

        return str(result.inserted_id)

    async def get_summary_by_id(self, summary_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a summary by its ID.

        Args:
            summary_id: ID of the summary to retrieve

        Returns:
            Optional[Dict[str, Any]]: Summary document if found, None otherwise
        """
        try:
            return await self.summaries.find_one({"_id": ObjectId(summary_id)})
        except Exception as e:
            log.error("Error retrieving summary by ID", error=str(e), summary_id=summary_id)
            return None

    async def get_summaries_by_chat(self, chat_id: int, limit: int = 10, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Get summaries for a specific chat.

        Args:
            chat_id: Chat ID to fetch summaries for
            limit: Maximum number of summaries to return
            skip: Number of summaries to skip (for pagination)

        Returns:
            List[Dict[str, Any]]: List of summary documents
        """
        cursor = self.summaries.find({"chat_id": chat_id}).sort("generated_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=None)

    async def get_summaries_by_date_range(self, chat_id: int, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """
        Get summaries for a specific chat within a date range.

        Args:
            chat_id: Chat ID to fetch summaries for
            start_date: Start date for the range
            end_date: End date for the range

        Returns:
            List[Dict[str, Any]]: List of summary documents
        """
        cursor = self.summaries.find({"chat_id": chat_id, "summary_date": {"$gte": start_date, "$lte": end_date}}).sort("summary_date", 1)

        return await cursor.to_list(length=None)

    async def get_latest_summary_for_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the most recent summary for a specific chat.

        Args:
            chat_id: Chat ID to fetch the latest summary for

        Returns:
            Optional[Dict[str, Any]]: Latest summary document if found, None otherwise
        """
        return await self.summaries.find_one({"chat_id": chat_id}, sort=[("generated_at", -1)])

    async def count_summaries_by_chat(self, chat_id: int) -> int:
        """
        Count the number of summaries for a specific chat.

        Args:
            chat_id: Chat ID to count summaries for

        Returns:
            int: Number of summaries for the chat
        """
        return await self.summaries.count_documents({"chat_id": chat_id})

    async def get_summary_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored summaries.

        Returns:
            Dict[str, Any]: Statistics about summaries
        """
        pipeline = [{"$group": {"_id": None, "total_summaries": {"$sum": 1}, "total_chats": {"$addToSet": "$chat_id"}, "avg_themes_per_summary": {"$avg": {"$size": "$themes"}}, "avg_message_count": {"$avg": "$message_count"}}}]

        result = await self.summaries.aggregate(pipeline).to_list(length=1)
        if not result:
            return {"total_summaries": 0, "total_chats": 0, "avg_themes_per_summary": 0, "avg_message_count": 0}

        stats = result[0]
        stats["total_chats"] = len(stats["total_chats"])
        return stats

    async def delete_summary(self, summary_id: str) -> bool:
        """
        Delete a summary by its ID.

        Args:
            summary_id: ID of the summary to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            result = await self.summaries.delete_one({"_id": ObjectId(summary_id)})
            return result.deleted_count > 0
        except Exception as e:
            log.error("Error deleting summary", error=str(e), summary_id=summary_id)
            return False
