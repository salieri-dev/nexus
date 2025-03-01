import structlog

from src.database.client import DatabaseClient
from src.database.repository.peer_config_repository import PeerConfigRepository
from .config import register_parameters

logger = structlog.get_logger(__name__)


async def initialize():
    """Initialize the falai plugin configuration."""
    try:
        # Get database client and peer config repository
        db_client = DatabaseClient.get_instance()
        peer_config_repo = PeerConfigRepository(db_client.client)

        # Register peer config parameters
        register_parameters()

        # Initialize new parameters for existing peers if needed
        await peer_config_repo.initialize_new_params()

        logger.info("Falai plugin configuration initialized")

    except Exception as e:
        logger.error(f"Error initializing falai plugin: {e}")
