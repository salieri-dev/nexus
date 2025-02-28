import asyncio
import time
from datetime import datetime
from typing import Dict, Tuple

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from src.database.client import DatabaseClient

logger = structlog.get_logger()


class RateLimitRepository:
    """Repository for handling rate limit operations."""

    # Class-level lock and cache
    _lock = asyncio.Lock()
    _cache: Dict[Tuple[int, str], float] = {}

    def __init__(self, db_client: DatabaseClient):
        self.db = db_client.db
        self.collection: AsyncIOMotorCollection = self.db["ratelimits"]

    async def initialize(self):
        """Initialize the rate limit collection with indexes."""
        # Create compound index on user_id and operation
        await self.collection.create_index([("user_id", 1), ("operation", 1)], unique=True)
        # Create TTL index to automatically remove old entries
        await self.collection.create_index(
            "timestamp",
            expireAfterSeconds=86400,  # 24 hours
        )

    async def check_rate_limit(self, user_id: int, operation: str, window_seconds: int) -> bool:
        """
        Check if operation is allowed using thread-safe class-level cache.

        Args:
            user_id: The user ID
            operation: The operation name
            window_seconds: Time window in seconds

        Returns:
            bool: True if operation is allowed, False if rate limited
        """
        key = (user_id, operation)
        current_time = time.time()

        async with self._lock:
            # Check cache
            last_request = self._cache.get(key, 0)
            if current_time - last_request < window_seconds:
                return False

            # Update cache immediately
            self._cache[key] = current_time

            # Update MongoDB asynchronously
            now = datetime.utcnow()
            try:
                await self.collection.update_one({"user_id": user_id, "operation": operation}, {"$set": {"timestamp": now}}, upsert=True)
            except Exception as e:
                logger.error("Failed to update rate limit in MongoDB", error=str(e))

            return True
