"""Image generation plugin for Nexus bot."""

import structlog

from src.plugins.imagegen.repository import ImagegenModelRepository

# Get the shared logger instance
logger = structlog.get_logger()


async def initialize():
    """Initialize imagegen plugin."""
    try:
        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        logger.info("Imagegen plugin initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize imagegen plugin", error=str(e))


# Export the initialization function
__all__ = ["initialize"]
