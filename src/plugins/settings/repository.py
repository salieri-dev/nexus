from typing import Dict, Optional
import structlog
from motor.motor_asyncio import AsyncIOMotorClient

logger = structlog.get_logger()

class PeerSettingsRepository:
    """Repository for managing peer settings"""

    def __init__(self, db):
        self.db = db["nexus"]
        self.collection = self.db["peers"]

    async def get_peer_settings(self, chat_id: int) -> Optional[Dict]:
        """Get settings for a specific peer."""
        return await self.collection.find_one({"_id": chat_id})

    async def update_peer_settings(self, chat_id: int, settings: Dict) -> bool:
        """Update settings for a specific peer."""
        try:
            result = await self.collection.update_one(
                {"_id": chat_id},
                {"$set": settings},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("Failed to update peer settings", 
                        error=str(e),
                        chat_id=chat_id)
            return False

    async def toggle_nsfw(self, chat_id: int, allowed: bool) -> bool:
        """Toggle NSFW setting for a peer."""
        try:
            result = await self.collection.update_one(
                {"_id": chat_id},
                {
                    "$set": {"nsfw_allowed": allowed},
                    "$setOnInsert": {"created_at": {"$date": "$$NOW"}}
                },
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("Failed to toggle NSFW setting",
                        error=str(e),
                        chat_id=chat_id)
            return False

    async def is_nsfw_allowed(self, chat_id: int) -> bool:
        """Check if NSFW content is allowed for a peer."""
        settings = await self.get_peer_settings(chat_id)
        return settings.get("nsfw_allowed", False) if settings else False