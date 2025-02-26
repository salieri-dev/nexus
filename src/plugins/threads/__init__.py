import os

import structlog

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


async def initialize():
    """Initialize the threads plugin configuration."""
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)

        # Read default system prompts from files
        bugurt_prompt_path = os.path.join(CURRENT_DIR, "defaults/bugurt_system_prompt.txt")
        greentext_prompt_path = os.path.join(CURRENT_DIR, "defaults/greentext_system_prompt.txt")

        bugurt_prompt = ""
        greentext_prompt = ""

        # Read bugurt prompt
        if os.path.exists(bugurt_prompt_path):
            with open(bugurt_prompt_path, 'r', encoding='utf-8') as file:
                bugurt_prompt = file.read()
        else:
            logger.error(f"File not found: {bugurt_prompt_path}")

        # Read greentext prompt
        if os.path.exists(greentext_prompt_path):
            with open(greentext_prompt_path, 'r', encoding='utf-8') as file:
                greentext_prompt = file.read()
        else:
            logger.error(f"File not found: {greentext_prompt_path}")

        # Default configuration
        default_config = {
            "BUGURT_SYSTEM_PROMPT": bugurt_prompt,
            "GREENTEXT_SYSTEM_PROMPT": greentext_prompt,
            "BUGURT_MODEL_NAME": "anthropic/claude-3.5-sonnet:beta",
            "GREENTEXT_MODEL_NAME": "anthropic/claude-3.5-sonnet:beta"
        }

        # Register plugin configuration
        await config_repo.register_plugin_config("threads", default_config)
        logger.info("Threads plugin configuration initialized")

    except Exception as e:
        logger.error(f"Error initializing threads plugin: {e}")
