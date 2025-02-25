from typing import Dict, Optional, Any, List
import os
import structlog

# Get the shared logger instance
logger = structlog.get_logger()


class BotConfigRepository:
    """Repository for handling global bot configuration."""

    def __init__(self, db_client):
        self.db = db_client.db
        self.collection = self.db["bot_config"]
        # In-memory cache of configurations
        self._config_cache = {}

    async def initialize(self):
        """
        Initialize the bot configuration if it doesn't exist.
        This should be called once during application startup.
        """
        # No default configurations are created here
        # Plugins will register their own configurations
        logger.info("Bot configuration repository initialized")
    
    @staticmethod
    def _read_file_content(file_path: str) -> str:
        """Read content from a file."""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as file:
                    return file.read()
            else:
                logger.error(f"File not found: {file_path}")
                return ""
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return ""
    
    async def get_config(self, config_id: str) -> Dict:
        """
        Get configuration by ID, using cache if available.
        Returns empty config if it doesn't exist.
        """
        # Check cache first
        if config_id in self._config_cache:
            return self._config_cache[config_id]
        
        # Check database
        config = await self.collection.find_one({"config_id": config_id})
        
        if not config:
            # Return empty config with just the ID
            config = {"config_id": config_id}
            await self.collection.insert_one(config)
            logger.info(f"Created empty configuration for {config_id}")
        
        # Cache the config
        self._config_cache[config_id] = config
        return config
    
    async def update_config(self, config_id: str, updates: Dict) -> Dict:
        """Update configuration with new values."""
        # Get current config
        current_config = await self.get_config(config_id)
        
        # Update database
        await self.collection.update_one(
            {"config_id": config_id},
            {"$set": updates},
            upsert=True
        )
        
        # Update cache
        if config_id in self._config_cache:
            self._config_cache[config_id].update(updates)
        else:
            await self.get_config(config_id)  # This will cache the config
        
        return self._config_cache[config_id]
    
    def invalidate_cache(self, config_id: str = None):
        """
        Invalidate the cache for a specific config_id or entire cache.
        """
        if config_id is not None:
            self._config_cache.pop(config_id, None)
        else:
            self._config_cache.clear()
    
    # Generic configuration methods for plugins
    
    async def register_plugin_config(self, plugin_id: str, default_config: Dict) -> Dict:
        """
        Register a plugin's configuration with default values if it doesn't exist.
        This should be called by plugins during their initialization.
        
        Args:
            plugin_id: Unique identifier for the plugin
            default_config: Default configuration values
            
        Returns:
            The current configuration (either existing or newly created)
        """
        # Check if config already exists
        config = await self.collection.find_one({"config_id": plugin_id})
        
        if not config:
            # Create new config with defaults
            config = {"config_id": plugin_id, **default_config}
            await self.collection.insert_one(config)
            logger.info(f"Registered default configuration for plugin: {plugin_id}")
            
            # Cache the config
            self._config_cache[plugin_id] = config
        
        return config
    
    async def get_plugin_config(self, plugin_id: str) -> Dict:
        """
        Get a plugin's configuration.
        
        Args:
            plugin_id: Unique identifier for the plugin
            
        Returns:
            The plugin's configuration
        """
        return await self.get_config(plugin_id)
    
    async def update_plugin_config(self, plugin_id: str, updates: Dict) -> Dict:
        """
        Update a plugin's configuration.
        
        Args:
            plugin_id: Unique identifier for the plugin
            updates: Configuration updates to apply
            
        Returns:
            The updated configuration
        """
        return await self.update_config(plugin_id, updates)
    
    async def get_plugin_config_value(self, plugin_id: str, key: str, default: Any = None) -> Any:
        """
        Get a specific value from a plugin's configuration.
        
        Args:
            plugin_id: Unique identifier for the plugin
            key: Configuration key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The configuration value or default
        """
        config = await self.get_config(plugin_id)
        return config.get(key, default)
    
    async def set_plugin_config_value(self, plugin_id: str, key: str, value: Any) -> Dict:
        """
        Set a specific value in a plugin's configuration.
        
        Args:
            plugin_id: Unique identifier for the plugin
            key: Configuration key to set
            value: Value to set
            
        Returns:
            The updated configuration
        """
        return await self.update_config(plugin_id, {key: value})
    
    async def reset_plugin_config(self, plugin_id: str, default_config: Dict) -> Dict:
        """
        Reset a plugin's configuration to default values.
        
        Args:
            plugin_id: Unique identifier for the plugin
            default_config: Default configuration values
            
        Returns:
            The reset configuration
        """
        # Keep only the config_id and update with defaults
        await self.collection.update_one(
            {"config_id": plugin_id},
            {"$set": default_config},
            upsert=True
        )
        
        # Invalidate cache for this config
        self.invalidate_cache(plugin_id)
        
        # Get and return the updated config
        return await self.get_config(plugin_id)