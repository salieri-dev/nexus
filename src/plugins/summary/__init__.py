import os
import structlog
from src.database.client import DatabaseClient
from src.database.bot_config_repository import BotConfigRepository

logger = structlog.get_logger(__name__)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

async def initialize():
    """Initialize the summary plugin configuration."""
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)
        
        # Read default system prompt from file
        prompt_path = os.path.join(CURRENT_DIR, "schemas/prompts.txt")
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
        await config_repo.register_plugin_config("summary", default_config)
        logger.info("Summary plugin configuration initialized")
        
    except Exception as e:
        logger.error(f"Error initializing summary plugin: {e}")