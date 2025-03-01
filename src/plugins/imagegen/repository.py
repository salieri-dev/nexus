"""Repository for imagegen plugin."""

from typing import Dict, Any, Optional, List

from structlog import get_logger

from src.config.framework import PeerConfigModel, update_chat_setting, get_chat_setting
from src.database.client import DatabaseClient
from .constants import DEFAULT_CONFIG

log = get_logger(__name__)


class ImagegenRepository:
    """Repository for handling imagegen settings in peer_config."""

    @staticmethod
    async def get_imagegen_config(chat_id: int) -> Dict[str, Any]:
        """
        Get imagegen configuration for a chat.

        Args:
            chat_id: The chat ID to get configuration for

        Returns:
            Dictionary with imagegen configuration
        """
        try:
            # Get the imagegen_cfg from peer_config
            config = await get_chat_setting(chat_id, "imagegen_cfg", None)

            # If config doesn't exist, initialize with defaults
            if not config:
                config = DEFAULT_CONFIG.copy()
                await ImagegenRepository.update_imagegen_config(chat_id, config)

            return config
        except Exception as e:
            log.error("Error getting imagegen config", error=str(e), chat_id=chat_id)
            return DEFAULT_CONFIG.copy()

    @staticmethod
    async def update_imagegen_config(chat_id: int, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update imagegen configuration for a chat.

        Args:
            chat_id: The chat ID to update configuration for
            config: The new configuration dictionary

        Returns:
            Updated configuration dictionary
        """
        try:
            # Update the imagegen_cfg in peer_config
            await update_chat_setting(chat_id, "imagegen_cfg", config)
            return config
        except Exception as e:
            log.error("Error updating imagegen config", error=str(e), chat_id=chat_id)
            return await ImagegenRepository.get_imagegen_config(chat_id)

    @staticmethod
    async def update_imagegen_setting(chat_id: int, setting: str, value: Any) -> Dict[str, Any]:
        """
        Update a specific setting in the imagegen configuration.

        Args:
            chat_id: The chat ID to update configuration for
            setting: The setting key to update
            value: The new value for the setting

        Returns:
            Updated configuration dictionary
        """
        try:
            # Get current config
            config = await ImagegenRepository.get_imagegen_config(chat_id)

            # Update the specific setting
            config[setting] = value

            # Save the updated config
            return await ImagegenRepository.update_imagegen_config(chat_id, config)
        except Exception as e:
            log.error("Error updating imagegen setting", error=str(e), chat_id=chat_id, setting=setting)
            return await ImagegenRepository.get_imagegen_config(chat_id)


class ImagegenModelRepository:
    """Repository for handling available models for image generation."""

    def __init__(self):
        """Initialize the repository with database client."""
        self.db_client = DatabaseClient.get_instance()
        self.db = self.db_client.db
        self.models_collection = self.db["imagegen_models"]

    async def initialize(self):
        """Initialize the repository by creating indexes."""
        try:
            # Create unique index on id field for models
            await self.models_collection.create_index("id", unique=True)

            log.info("ImagegenModelRepository initialized successfully")
        except Exception as e:
            log.error("Error initializing ImagegenModelRepository", error=str(e))

    async def add_model(self, id: str, name: str, url: str, description: str = "", type: str = "MODEL", preview_url: str = "") -> Dict[str, Any]:
        """
        Add a new model to the database.

        Args:
            id: The unique identifier of the model
            name: The display name of the model
            url: The URL or identifier of the model
            description: Optional description of the model
            type: The type of model (e.g., "MODEL", "CHECKPOINT", "MERGED")
            preview_url: Optional URL to a preview image of the model

        Returns:
            The added model document
        """
        try:
            model = {"id": id, "name": name, "url": url, "description": description, "type": type, "is_active": True, "preview_url": preview_url}

            # Insert the model
            result = await self.models_collection.insert_one(model)
            model["_id"] = result.inserted_id

            log.info("Added new model", id=id, name=name, type=type)
            return model
        except Exception as e:
            log.error("Error adding model", error=str(e), id=id, name=name)
            raise

    async def get_all_models(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get all models from the database.

        Args:
            active_only: If True, only return active models

        Returns:
            List of model documents
        """
        try:
            query = {"type": {"$ne": "LORA"}}  # Exclude LORA type
            if active_only:
                query["is_active"] = True
                
            cursor = self.models_collection.find(query)
            models = await cursor.to_list(length=None)
            return models
        except Exception as e:
            log.error("Error getting models", error=str(e))
            return []

    async def get_model_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Get a model by id.

        Args:
            id: The id of the model

        Returns:
            The model document or None if not found
        """
        try:
            # First try to find a model with the exact id
            model = await self.models_collection.find_one({"id": id})
            
            # If found, return it regardless of type
            return model
        except Exception as e:
            log.error("Error getting model by id", error=str(e), id=id)
            return None

    async def get_model_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a model by name.

        Args:
            name: The name of the model

        Returns:
            The model document or None if not found
        """
        try:
            # First try to find a model with the exact name and not of type LORA
            model = await self.models_collection.find_one({"name": name, "type": {"$ne": "LORA"}})
            
            # If found, return it
            if model:
                return model
                
            # If not found, try to find any model with the exact name
            return await self.models_collection.find_one({"name": name})
        except Exception as e:
            log.error("Error getting model by name", error=str(e), name=name)
            return None

    async def update_model(self, id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a model.

        Args:
            id: The id of the model to update
            updates: The updates to apply

        Returns:
            The updated model document or None if not found
        """
        try:
            # Update the model with the given id and not of type LORA
            result = await self.models_collection.update_one({"id": id, "type": {"$ne": "LORA"}}, {"$set": updates})

            if result.matched_count == 0:
                log.warning("Model not found for update", id=id)
                return None

            log.info("Updated model", id=id)
            return await self.get_model_by_id(id)
        except Exception as e:
            log.error("Error updating model", error=str(e), id=id)
            return None

    async def delete_model(self, id: str) -> bool:
        """
        Delete a model.

        Args:
            id: The id of the model to delete

        Returns:
            True if the model was deleted, False otherwise
        """
        try:
            # Delete the model with the given id and not of type LORA
            result = await self.models_collection.delete_one({"id": id, "type": {"$ne": "LORA"}})
            success = result.deleted_count > 0

            if success:
                log.info("Deleted model", id=id)
            else:
                log.warning("Model not found for deletion", id=id)

            return success
        except Exception as e:
            log.error("Error deleting model", error=str(e), id=id)
            return False

    async def add_lora(self, id: str, name: str, url: str, description: str = "", default_scale: float = 0.7, trigger_words: str = "", type: str = "LORA", preview_url: str = "") -> Dict[str, Any]:
        """
        Add a new lora to the database.

        Args:
            id: The unique identifier of the lora
            name: The display name of the lora
            url: The URL or identifier of the lora
            description: Optional description of the lora
            default_scale: Default scale/weight for the lora (default: 0.7)
            trigger_words: Words to add to the prompt when using this lora
            type: The type of lora (default: "LORA")
            preview_url: Optional URL to a preview image of the lora

        Returns:
            The added lora document
        """
        try:
            lora = {"id": id, "name": name, "url": url, "description": description, "default_scale": default_scale, "trigger_words": trigger_words, "type": type, "is_active": True, "preview_url": preview_url}

            # Insert the lora into the models collection
            result = await self.models_collection.insert_one(lora)
            lora["_id"] = result.inserted_id

            log.info("Added new lora", id=id, name=name, type=type)
            return lora
        except Exception as e:
            log.error("Error adding lora", error=str(e), id=id, name=name)
            raise

    async def get_all_loras(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get all loras from the database.

        Args:
            active_only: If True, only return active loras

        Returns:
            List of lora documents
        """
        try:
            query = {"type": "LORA"}
            if active_only:
                query["is_active"] = True
                
            cursor = self.models_collection.find(query)
            loras = await cursor.to_list(length=None)
            return loras
        except Exception as e:
            log.error("Error getting loras", error=str(e))
            return []

    async def get_lora_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """
        Get a lora by id.

        Args:
            id: The id of the lora

        Returns:
            The lora document or None if not found
        """
        try:
            return await self.models_collection.find_one({"id": id, "type": "LORA"})
        except Exception as e:
            log.error("Error getting lora by id", error=str(e), id=id)
            return None

    async def get_lora_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a lora by name.

        Args:
            name: The name of the lora

        Returns:
            The lora document or None if not found
        """
        try:
            return await self.models_collection.find_one({"name": name, "type": "LORA"})
        except Exception as e:
            log.error("Error getting lora by name", error=str(e), name=name)
            return None

    async def update_lora(self, id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Update a lora.

        Args:
            id: The id of the lora to update
            updates: The updates to apply

        Returns:
            The updated lora document or None if not found
        """
        try:
            result = await self.models_collection.update_one({"id": id, "type": "LORA"}, {"$set": updates})

            if result.matched_count == 0:
                log.warning("Lora not found for update", id=id)
                return None

            log.info("Updated lora", id=id)
            return await self.get_lora_by_id(id)
        except Exception as e:
            log.error("Error updating lora", error=str(e), id=id)
            return None

    async def delete_lora(self, id: str) -> bool:
        """
        Delete a lora.

        Args:
            id: The id of the lora to delete

        Returns:
            True if the lora was deleted, False otherwise
        """
        try:
            result = await self.models_collection.delete_one({"id": id, "type": "LORA"})
            success = result.deleted_count > 0

            if success:
                log.info("Deleted lora", id=id)
            else:
                log.warning("Lora not found for deletion", id=id)

            return success
        except Exception as e:
            log.error("Error deleting lora", error=str(e), id=id)
            return False

    async def get_models_dict(self) -> Dict[str, Dict[str, str]]:
        """
        Get all models as a dictionary mapping id to model details.

        Returns:
            Dictionary with model ids as keys and model details as values
        """
        try:
            # Get models that are not of type LORA
            query = {"is_active": True, "type": {"$ne": "LORA"}}
            cursor = self.models_collection.find(query)
            models = await cursor.to_list(length=None)
            return {model["id"]: {"url": model["url"], "preview_url": model.get("preview_url", "")} for model in models}
        except Exception as e:
            log.error("Error getting models dict", error=str(e))
            return {}

    async def get_loras_dict(self) -> Dict[str, Dict[str, str]]:
        """
        Get all loras as a dictionary mapping id to lora details.

        Returns:
            Dictionary with lora ids as keys and lora details as values
        """
        try:
            loras = await self.get_all_loras(active_only=True)
            return {lora["id"]: {"url": lora["url"], "preview_url": lora.get("preview_url", "")} for lora in loras}
        except Exception as e:
            log.error("Error getting loras dict", error=str(e))
            return {}


# Register the imagegen_cfg parameter in the peer_config model
PeerConfigModel.register_param(param_name="imagegen_cfg", param_type="plugin:imagegen", default=DEFAULT_CONFIG.copy(), description="Настройки генерации изображений", display_name="Настройки генерации изображений", command_name="imagegen")
