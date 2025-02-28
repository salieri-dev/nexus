import os

import structlog

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.database.repository.peer_config_repository import PeerConfigRepository
from .config import register_parameters
from .repository import SummaryRepository

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


async def initialize():
    """Initialize the summary plugin configuration."""
    try:
        # Get database client and repositories
        db_client = DatabaseClient.get_instance()
        bot_config_repo = BotConfigRepository(db_client)
        peer_config_repo = PeerConfigRepository(db_client.client)
        summary_repo = SummaryRepository(db_client.client)
        
        # Create indexes for summary repository
        await summary_repo.create_indexes()

        # Read default system prompt from file
        prompt_path = os.path.join(CURRENT_DIR, "default_system_prompt.txt")
        system_prompt = ""

        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as file:
                system_prompt = file.read()
        else:
            logger.error(f"File not found: {prompt_path}")

        # Default configuration
        default_config = {
            "SUMMARY_SYSTEM_PROMPT": system_prompt,
            "SUMMARY_MODEL_NAME": "openai/gpt-4o-mini",
            "SUMMARY_MIN_MESSAGES_THRESHOLD": 60
        }

        # Register plugin configuration
        await bot_config_repo.register_plugin_config("summary", default_config)
        
        # Register peer config parameters
        register_parameters()
        
        # Initialize new parameters for existing peers if needed
        await peer_config_repo.initialize_new_params()
        
        logger.info("Summary plugin configuration initialized")

    except Exception as e:
        logger.error(f"Error initializing summary plugin: {e}")
