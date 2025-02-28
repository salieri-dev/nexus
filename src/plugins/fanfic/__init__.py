import os

import structlog

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


async def initialize():
    """Initialize the fanfic plugin configuration."""
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)

        # Default fanfic system prompt (family-friendly version)
        prompt_path = os.path.join(CURRENT_DIR, "default_system_prompt.txt")
        system_prompt = ""

        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as file:
                system_prompt = file.read()
        else:
            logger.error(f"File not found: {prompt_path}")

        # Default configuration
        default_config = {"FANFIC_SYSTEM_PROMPT": system_prompt, "FANFIC_MODEL_NAME": "x-ai/grok-2-1212"}

        # Register plugin configuration
        await config_repo.register_plugin_config("fanfic", default_config)
        logger.info("Fanfic plugin configuration initialized")

    except Exception as e:
        logger.error(f"Error initializing fanfic plugin: {e}")
