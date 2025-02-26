import os
import structlog
from src.database.client import DatabaseClient
from src.database.bot_config_repository import BotConfigRepository

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

async def initialize():
    """Initialize the deathbyai plugin configuration."""
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)
        
        # Default configuration
        default_config = {
            "DEATHBYAI_MODEL_NAME": "anthropic/claude-3.5-sonnet:beta",
            "DEATHBYAI_GAME_DURATION_MINUTES": 1,
            "DEATHBYAI_EVALUATION_TEMPERATURE": 0.7
        }
        
        # Register plugin configuration
        await config_repo.register_plugin_config("deathbyai", default_config)
        logger.info("DeathByAI plugin configuration initialized")
        
    except Exception as e:
        logger.error(f"Error initializing deathbyai plugin: {e}")
