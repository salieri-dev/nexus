from datetime import datetime, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorCollection
import structlog
from src.database.client import DatabaseClient

logger = structlog.get_logger()


class RateLimitRepository:
    """Repository for handling rate limit operations using timestamps."""

    def __init__(self, db_client: DatabaseClient):
        self.db = db_client.db
        self.collection: AsyncIOMotorCollection = self.db["ratelimits"]

    async def initialize(self):
        """Initialize the rate limit collection with indexes."""
        # Create compound index on user_id and operation
        await self.collection.create_index(
            [("user_id", 1), ("operation", 1)],
            unique=True
        )
        # Create TTL index to automatically remove old entries
        await self.collection.create_index(
            "timestamp",
            expireAfterSeconds=86400  # 24 hours
        )

    async def check_rate_limit(
        self,
        user_id: int,
        operation: str,
        window_seconds: int
    ) -> bool:
        """
        Check if operation is allowed based on timestamp.
        
        Args:
            user_id: The user ID
            operation: The operation name
            window_seconds: Time window in seconds
            
        Returns:
            bool: True if operation is allowed, False if rate limited
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=window_seconds)

        # Try to find recent request
        result = await self.collection.find_one({
            "user_id": user_id,
            "operation": operation,
            "timestamp": {"$gt": window_start}
        })

        if result:
            # Found recent request, rate limit
            return False

        # No recent request found, allow and record timestamp
        await self.collection.update_one(
            {"user_id": user_id, "operation": operation},
            {
                "$set": {
                    "timestamp": now
                }
            },
            upsert=True
        )
        return True