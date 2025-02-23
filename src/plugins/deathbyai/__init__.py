"""Death by AI game plugin"""
import structlog
from src.database.client import DatabaseClient
from src.plugins.deathbyai.repository import DeathByAIRepository
from src.plugins.deathbyai.service import DeathByAIService
from .deathbyai import start_game_command, handle_strategy, end_game_callback

# Get the shared logger instance
logger = structlog.get_logger()

async def init_deathbyai():
    """Initialize Death by AI plugin and create indexes."""
    try:
        # Get shared database instance
        db_client = DatabaseClient.get_instance()

        # Initialize repository
        repository = DeathByAIRepository(db_client.client)

        # Create indexes
        await repository.create_indexes()
        logger.info("Death by AI indexes created")
    except Exception as e:
        logger.error("Failed to create Death by AI indexes", error=str(e))

# Export the initialization function and handlers
__all__ = ['init_deathbyai', 'start_game_command', 'handle_strategy', 'end_game_callback']