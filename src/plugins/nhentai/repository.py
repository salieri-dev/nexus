"""Repository for nhentai plugin database operations"""

from typing import Optional, Dict, Any

from pymongo.database import Database
from structlog import get_logger

log = get_logger(__name__)


class NhentaiRepository:
    """Repository for nhentai plugin database operations"""

    def __init__(self, db_client: Database):
        """Initialize repository with database client"""
        self.db = db_client
        self.collection = self.db.nhentai_settings

    async def get_blur_setting(self, chat_id: int) -> bool:
        """Get nhentai_blur setting from database"""
        try:
            result = await self.collection.find_one({"chat_id": chat_id})
            if result and "nhentai_blur" in result:
                return result["nhentai_blur"]
            return True  # Default to blur enabled
        except Exception as e:
            log.error("Failed to get blur setting", error=str(e), chat_id=chat_id)
            return True  # Default to blur enabled if error

    async def set_blur_setting(self, chat_id: int, blur_enabled: bool) -> bool:
        """Set nhentai_blur setting in database"""
        try:
            await self.collection.update_one(
                {"chat_id": chat_id},
                {"$set": {"nhentai_blur": blur_enabled}},
                upsert=True
            )
            return True
        except Exception as e:
            log.error("Failed to set blur setting", error=str(e), chat_id=chat_id)
            return False