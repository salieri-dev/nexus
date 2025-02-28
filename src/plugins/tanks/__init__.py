import structlog

from src.database.client import DatabaseClient
from src.plugins.tanks.repository import TanksRepository
from src.plugins.tanks.service import TankService

# Get the shared logger instance
logger = structlog.get_logger()


async def init_tanks():
    """Initialize tanks plugin and sync data."""
    try:
        # Get shared database instance
        db_client = DatabaseClient.get_instance()

        # Initialize repository and service
        tanks_repo = TanksRepository(db_client.client)
        tank_service = TankService(tanks_repo)

        # Sync tanks
        synced_count = await tank_service.sync_tanks(clear_existing=False)
        logger.info("Initial tank sync completed", count=synced_count)
    except Exception as e:
        logger.error("Failed initial tank sync", error=str(e))


# Export the initialization function
__all__ = ["init_tanks"]
