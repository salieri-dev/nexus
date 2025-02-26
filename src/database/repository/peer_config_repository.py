from typing import Dict, Any, Optional
import structlog
from pydantic import ValidationError

from src.config.framework import PeerConfigModel

logger = structlog.get_logger(__name__)

class PeerConfigRepository:
    """Enhanced repository for handling peer-specific configurations."""

    def __init__(self, db):
        self.db = db["nexus"]
        self.collection = self.db["peer_config"]
        # In-memory cache of peer configurations
        self._config_cache = {}

    async def initialize_new_params(self):
        """
        Initialize any new parameters for all existing peers.
        This should be called after all plugins have registered their parameters.
        """
        # Get all peers
        all_peers = await self.collection.find({}).to_list(length=None)
        
        # For each peer, check for missing parameters and add defaults
        for peer_doc in all_peers:
            chat_id = peer_doc.get("chat_id")
            if not chat_id:
                continue
                
            updates = {}
            # Check each registered parameter
            for param_name, param_info in PeerConfigModel.param_registry.items():
                if param_name not in peer_doc:
                    # Parameter doesn't exist for this peer, add with default
                    updates[param_name] = param_info.default
            
            if updates:
                # Update the peer with new parameters
                await self.collection.update_one(
                    {"chat_id": chat_id},
                    {"$set": updates}
                )
                logger.info(
                    "Initialized new parameters for peer",
                    chat_id=chat_id,
                    parameters=list(updates.keys())
                )
                
                # Update cache if needed
                if chat_id in self._config_cache:
                    self._config_cache[chat_id].update(updates)
        
        logger.info("Completed parameter initialization for all peers")

    async def get_peer_config(self, chat_id: int) -> Dict:
        """
        Get peer configuration, using cache if available.
        Creates default config if peer doesn't exist.
        Ensures all registered parameters exist.
        """
        # Check cache first
        if chat_id in self._config_cache:
            return self._config_cache[chat_id]

        # Check database
        config = await self.collection.find_one({"chat_id": chat_id})

        if not config:
            # Create new config with defaults from registry
            default_values = {
                field: info.default
                for field, info in PeerConfigModel.param_registry.items()
            }
            config = {"chat_id": chat_id, **default_values}
            await self.collection.insert_one(config)
            logger.info(f"Created new configuration for chat {chat_id}")
        else:
            # Check for missing parameters
            updates = {}
            for param_name, param_info in PeerConfigModel.param_registry.items():
                if param_name not in config:
                    updates[param_name] = param_info.default
                    config[param_name] = param_info.default
            
            if updates:
                # Update with missing parameters
                await self.collection.update_one(
                    {"chat_id": chat_id},
                    {"$set": updates}
                )
                logger.info(
                    "Added missing parameters to config",
                    chat_id=chat_id,
                    parameters=list(updates.keys())
                )

        # Cache the config
        self._config_cache[chat_id] = config
        return config

    async def update_peer_config(self, chat_id: int, updates: Dict) -> Dict:
        """
        Update peer configuration with new values.
        Validates updates against registered parameters.
        """
        # Get current config to merge with updates
        current_config = await self.get_peer_config(chat_id)
        
        # Validate updates using our custom validation method
        valid_updates = {}
        for key, value in updates.items():
            if key in PeerConfigModel.param_registry:
                # Use our custom validation function
                is_valid, validated_value = PeerConfigModel.validate_param_value(key, value)
                if is_valid:
                    valid_updates[key] = validated_value
                else:
                    logger.error(
                        f"Validation error for parameter {key}",
                        chat_id=chat_id,
                        value=value
                    )
        
        if not valid_updates:
            return current_config
        
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
