import os

import structlog

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.database.repository.peer_config_repository import PeerConfigRepository
from .config import register_parameters

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


async def initialize():
    """Initialize the deathbyai plugin configuration."""
    try:
        # Get database client and config repositories
        db_client = DatabaseClient.get_instance()
        bot_config_repo = BotConfigRepository(db_client)
        peer_config_repo = PeerConfigRepository(db_client.client)

        # Default configuration
        default_config = {
            "DEATHBYAI_MODEL_NAME": "anthropic/claude-3.5-sonnet:beta",
            "DEATHBYAI_GAME_DURATION_MINUTES": 1,
            "DEATHBYAI_EVALUATION_TEMPERATURE": 0.7
        }

        # Register plugin configuration
        await bot_config_repo.register_plugin_config("deathbyai", default_config)
        
        # Register peer config parameters
        register_parameters()
        
        # Initialize new parameters for existing peers if needed
        await peer_config_repo.initialize_new_params()
        
        logger.info("DeathByAI plugin configuration initialized")

    except Exception as e:
        logger.error(f"Error initializing deathbyai plugin: {e}")
