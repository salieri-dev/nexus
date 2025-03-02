from typing import Dict, Optional, Any, ClassVar

import structlog
from pydantic import BaseModel, Field

from src.database.client import DatabaseClient

logger = structlog.get_logger(__name__)


class ConfigParam(BaseModel):
    """Base class for configuration parameters with metadata."""

    default: Any
    description: str
    display_name: str
    param_type: str = "core"  # "core" or "plugin:<plugin_id>"
    command_name: str  # User-friendly command name (e.g., "nsfw" instead of "nsfw_enabled")

    class Config:
        extra = "forbid"


class PeerConfigModel(BaseModel):
    """Base model for peer configuration with core parameters only."""

    # Only NSFW is a core parameter
    nsfw_enabled: bool = Field(default=False, description="Разрешен ли 18+ контент?", display_name="Разрешен ли 18+ контент?")
    
    # VIP status - not exposed via /config
    is_vip: bool = Field(default=False, description="VIP статус", display_name="VIP статус")

    # Class variables to store parameter metadata and mappings
    param_registry: ClassVar[Dict[str, ConfigParam]] = {}
    command_to_param: ClassVar[Dict[str, str]] = {}  # Maps command names to parameter names

    @classmethod
    def register_param(cls, param_name: str, param_type: str, default: Any, description: str, display_name: str, command_name: Optional[str] = None):
        """
        Register a parameter's metadata.

        Args:
            param_name: The parameter name in the database
            param_type: "core" or "plugin:<plugin_id>"
            default: Default value
            description: User-friendly description
            display_name: User-friendly display name
            command_name: User-friendly command name (defaults to param_name)
        """
        # If command_name is not provided, use param_name or strip _enabled suffix
        if command_name is None:
            command_name = param_name.replace("_enabled", "") if param_name.endswith("_enabled") else param_name

        # Register the parameter
        cls.param_registry[param_name] = ConfigParam(default=default, description=description, display_name=display_name, param_type=param_type, command_name=command_name)

        # Add to command mapping
        cls.command_to_param[command_name.lower()] = param_name

    @classmethod
    def register_core_params(cls):
        """Register core parameters defined in the model."""
        for field_name, field_info in cls.model_fields.items():
            default = field_info.default
            description = field_info.description or f"Parameter {field_name}"
            display_name = field_info.json_schema_extra.get("display_name", field_name) if field_info.json_schema_extra else field_name

            # Use "nsfw" as command name for "nsfw_enabled"
            command_name = field_name.replace("_enabled", "") if field_name.endswith("_enabled") else field_name

            cls.register_param(param_name=field_name, param_type="core", default=default, description=description, display_name=display_name, command_name=command_name)

    @classmethod
    def get_param_by_command(cls, command_name: str) -> Optional[str]:
        """
        Get parameter name from command name.

        Args:
            command_name: User-friendly command name

        Returns:
            Parameter name or None if not found
        """
        return cls.command_to_param.get(command_name.lower())

    @classmethod
    def validate_param_value(cls, param_name: str, value: Any) -> tuple[bool, Any]:
        """
        Validate a parameter value against its type.

        Args:
            param_name: Parameter name
            value: The value to validate

        Returns:
            Tuple of (is_valid, converted_value)
        """
        if param_name not in cls.param_registry:
            return False, None

        param_info = cls.param_registry[param_name]
        default = param_info.default

        # Determine the type from the default value
        param_type = type(default)

        try:
            # Handle different types
            if param_type == bool:
                if isinstance(value, str):
                    return True, value.lower() in ("true", "yes", "1", "on", "enable")
                return True, bool(value)
            elif param_type == int:
                return True, int(value)
            elif param_type == float:
                return True, float(value)
            elif param_type == str:
                return True, str(value)
            else:
                # For unknown types, just return as is
                return True, value
        except (ValueError, TypeError):
            # If conversion fails, return the default
            return False, default


async def get_chat_setting(chat_id: int, param_name: str, default=None):
    """
    Get a specific setting value for a chat.

    Args:
        chat_id: The chat ID to get configuration for
        param_name: The setting key to get (can be command name or parameter name)
        default: Default value if setting is not found

    Returns:
        The setting value
    """
    try:
        # Initialize repository
        from src.database.repository.peer_config_repository import PeerConfigRepository

        db_client = DatabaseClient.get_instance()
        config_repo = PeerConfigRepository(db_client.client)

        # Convert command name to parameter name if needed
        actual_param = PeerConfigModel.get_param_by_command(param_name) or param_name

        # Get current config
        config = await config_repo.get_peer_config(chat_id)

        # Return the value or default
        return config.get(actual_param, default)

    except Exception as e:
        logger.error("Error getting chat setting", error=str(e), chat_id=chat_id, setting=param_name)
        return default


async def update_chat_setting(chat_id: int, param_name: str, value: Any):
    """
    Update a specific setting value for a chat.

    Args:
        chat_id: The chat ID to update configuration for
        param_name: The setting key to update (can be command name or parameter name)
        value: The new value to set

    Returns:
        The updated configuration
    """
    try:
        # Initialize repository
        from src.database.repository.peer_config_repository import PeerConfigRepository

        db_client = DatabaseClient.get_instance()
        config_repo = PeerConfigRepository(db_client.client)

        # Convert command name to parameter name if needed
        actual_param = PeerConfigModel.get_param_by_command(param_name) or param_name

        # Update the specific parameter
        return await config_repo.update_peer_config(chat_id, {actual_param: value})

    except Exception as e:
        logger.error("Error updating chat setting", error=str(e), chat_id=chat_id, setting=param_name, value=value)
        # Get current config to return
        return await get_chat_config(chat_id)


async def get_chat_config(chat_id: int):
    """
    Get the full configuration for a chat.

    Args:
        chat_id: The chat ID to get configuration for

    Returns:
        The full configuration dictionary
    """
    try:
        # Initialize repository
        from src.database.repository.peer_config_repository import PeerConfigRepository

        db_client = DatabaseClient.get_instance()
        config_repo = PeerConfigRepository(db_client.client)

        # Get and return the config
        return await config_repo.get_peer_config(chat_id)

    except Exception as e:
        logger.error("Error getting chat config", error=str(e), chat_id=chat_id)
        return {"chat_id": chat_id}


def get_param_registry():
    """
    Get the parameter registry.

    Returns:
        Dictionary of registered parameters
    """
    return PeerConfigModel.param_registry


def get_param_info(param_name: str) -> Optional[ConfigParam]:
    """
    Get information about a specific parameter.

    Args:
        param_name: The parameter name or command name

    Returns:
        Parameter information or None if not found
    """
    # Check if it's a direct parameter name
    if param_name in PeerConfigModel.param_registry:
        return PeerConfigModel.param_registry[param_name]

    # Check if it's a command name
    actual_param = PeerConfigModel.get_param_by_command(param_name)
    if actual_param:
        return PeerConfigModel.param_registry.get(actual_param)

    return None


async def enable_vip(chat_id: int) -> Dict:
    """
    Enable VIP status for a chat.

    Args:
        chat_id: The chat ID to enable VIP for

    Returns:
        The updated configuration
    """
    return await update_chat_setting(chat_id, "is_vip", True)


async def disable_vip(chat_id: int) -> Dict:
    """
    Disable VIP status for a chat.

    Args:
        chat_id: The chat ID to disable VIP for

    Returns:
        The updated configuration
    """
    return await update_chat_setting(chat_id, "is_vip", False)


async def is_vip(chat_id: int) -> bool:
    """
    Check if a chat has VIP status.

    Args:
        chat_id: The chat ID to check

    Returns:
        True if the chat has VIP status, False otherwise
    """
    return await get_chat_setting(chat_id, "is_vip", False)


# Initialize core parameters
PeerConfigModel.register_core_params()
