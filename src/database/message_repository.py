from typing import Dict, List, Optional

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
        query = {"chat_id": chat_id}
        cursor = self.collection.find(query).limit(limit)
        return await cursor.to_list(length=None)

    async def get_messages_by_user(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get messages from a specific user."""
        query = {"user_id": user_id}
        cursor = self.collection.find(query).limit(limit)
        return await cursor.to_list(length=None)

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


class PeerRepository:
    """Repository for handling peer-specific configurations."""

    DEFAULT_CONFIG = {
        "nsfw_enabled": False,
        "transcribe_enabled": True,
        "summary_enabled": False,
        "nhentai_blur": True
    }

    def __init__(self, db):
        self.db = db["nexus"]
        self.collection = self.db["settings"]
        # In-memory cache of peer configurations
        self._config_cache = {}

    async def get_peer_config(self, chat_id: int) -> Dict:
        """
        Get peer configuration, using cache if available.
        Creates default config if peer doesn't exist.
        """
        # Check cache first
        if chat_id in self._config_cache:
            return self._config_cache[chat_id]

        # Check database
        config = await self.collection.find_one({"chat_id": chat_id})
        
        if not config:
            # Create new config with defaults
            config = {"chat_id": chat_id, **self.DEFAULT_CONFIG}
            await self.collection.insert_one(config)
        
        # Cache the config
        self._config_cache[chat_id] = config
        return config

    async def update_peer_config(self, chat_id: int, updates: Dict) -> Dict:
        """Update peer configuration with new values."""
        # Validate updates
        valid_updates = {k: v for k, v in updates.items() if k in self.DEFAULT_CONFIG}
        
        if not valid_updates:
            return await self.get_peer_config(chat_id)

        # Update database
        await self.collection.update_one(
            {"chat_id": chat_id},
            {"$set": valid_updates},
            upsert=True
        )

        # Update cache
        if chat_id in self._config_cache:
            self._config_cache[chat_id].update(valid_updates)
        else:
            await self.get_peer_config(chat_id)  # This will cache the config

        return self._config_cache[chat_id]

    def invalidate_cache(self, chat_id: int = None):
        """
        Invalidate the cache for a specific chat_id or entire cache.
        """
        if chat_id is not None:
            self._config_cache.pop(chat_id, None)
        else:
            self._config_cache.clear()
