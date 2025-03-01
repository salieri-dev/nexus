"""Image generation plugin for Nexus bot."""

import structlog

from src.database.client import DatabaseClient
from src.plugins.imagegen.repository import ImagegenModelRepository
from src.plugins.imagegen.service import ImagegenService

# Get the shared logger instance
logger = structlog.get_logger()


async def initialize():
    """Initialize imagegen plugin and add user-specified models and loras."""
    try:
        # Initialize repository
        repo = ImagegenModelRepository()
        await repo.initialize()

        # We'll initialize the service when it's first used, not during plugin initialization
        # This avoids initializing it twice (once here and once in the module)

        # Add user-specified models
        models = [
            {"id": "wai_illistrious", "civitai_id": 827184, "name": "Модель аниме", "url": "https://civitai.com/api/download/models/1410435?type=Model&format=SafeTensor&size=pruned&fp=fp16", "description": "NSFW model from Civitai"},
            {"id": "real_dream", "civitai_id": 153568, "name": "Модель с уклоном в фотореализм", "url": "https://civitai.com/api/download/models/1376263?type=Model&format=SafeTensor&size=pruned&fp=fp16", "description": "Realistic model from Civitai"},
        ]

        # Add user-specified loras
        loras = [{"id": "dungeon_squad_style", "civitai_id": 486237, "name": "Dungeon Squad Style", "url": "https://civitai.com/api/download/models/1399376?type=Model&format=SafeTensor", "description": "Dungeon style lora from Civitai", "default_scale": 1.0, "trigger_words": "pixel art"}]

        # Add models to database
        for model in models:
            try:
                existing_model = await repo.get_model_by_id(model["id"])
                if not existing_model:
                    await repo.add_model(model["id"], model["name"], model["url"], model["description"])
                    logger.info("Added model", id=model["id"], name=model["name"])
            except Exception as e:
                logger.error("Error adding model", id=model["id"], name=model["name"], error=str(e))

        # Add loras to database
        for lora in loras:
            try:
                existing_lora = await repo.get_lora_by_id(lora["id"])
                if not existing_lora:
                    await repo.add_lora(lora["id"], lora["name"], lora["url"], lora["description"], lora.get("default_scale", 0.7), lora.get("trigger_words", ""))
                    logger.info("Added lora", id=lora["id"], name=lora["name"])
            except Exception as e:
                logger.error("Error adding lora", id=lora["id"], name=lora["name"], error=str(e))

        logger.info("Imagegen plugin initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize imagegen plugin", error=str(e))


# Export the initialization function
__all__ = ["initialize"]
