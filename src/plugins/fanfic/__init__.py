import structlog
from src.database.client import DatabaseClient
from src.database.bot_config_repository import BotConfigRepository

logger = structlog.get_logger(__name__)

async def initialize():
    """Initialize the fanfic plugin configuration."""
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)
        
        # Default fanfic system prompt (family-friendly version)
        fanfic_prompt = """You are a creative writer specializing in family-friendly fanfiction.
Your task is to create an engaging, well-structured fanfiction based on the topic provided by the user.

Guidelines:
- Create a fanfiction of approximately 500-1000 words
- Include a title for the fanfiction
- Write in a narrative style with proper paragraphs
- Include dialogue where appropriate
- Content should be appropriate for all ages
- Focus on character development, plot, and storytelling
- You can include humor and light-hearted moments
- Describe characters' appearance, traits, and actions in an appropriate way
- Include a satisfying conclusion or epilogue
- Write in Russian language
"""
        
        # Default configuration
        default_config = {
            "FANFIC_SYSTEM_PROMPT": fanfic_prompt,
            "FANFIC_MODEL_NAME": "anthropic/claude-3.5-sonnet:beta"
        }
        
        # Register plugin configuration
        await config_repo.register_plugin_config("fanfic", default_config)
        logger.info("Fanfic plugin configuration initialized")
        
    except Exception as e:
        logger.error(f"Error initializing fanfic plugin: {e}")