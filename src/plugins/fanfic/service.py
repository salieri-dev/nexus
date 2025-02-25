from typing import Optional

from pydantic import BaseModel, Field
from structlog import get_logger

from src.services.openrouter import OpenRouter
from src.database.client import DatabaseClient
from src.database.bot_config_repository import BotConfigRepository

log = get_logger(__name__)

# Pydantic model for fanfic response
class FanficResponse(BaseModel):
    """Pydantic model for fanfic response"""
    title: str = Field(description="The title of the fanfiction")
    content: str = Field(description="The full text of the fanfiction")


async def generate_fanfic(topic: str) -> Optional[FanficResponse]:
    """
    Generate a fanfiction based on the given topic using OpenRouter API.
    
    Args:
        topic: The topic/theme for the fanfiction
        
    Returns:
        Optional[FanficResponse]: Pydantic model containing the title and content of the generated fanfiction,
                                  or None if generation failed
    """
    try:
        # Get database client and config repository
        db_client = DatabaseClient.get_instance()
        config_repo = BotConfigRepository(db_client)
        
        # Get system prompt and model name from config
        system_prompt = await config_repo.get_plugin_config_value("fanfic", "FANFIC_SYSTEM_PROMPT", "")
        model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME", "anthropic/claude-3.5-sonnet:beta")
        
        open_router = OpenRouter().client
        
        # Create the completion request using Pydantic model
        completion = await open_router.beta.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Создай фанфик на тему '{topic}'."
                }
            ],
            model=model_name,
            temperature=1,
            max_tokens=4000,
            response_format=FanficResponse,
            seed=42
        )
        
        log.info(completion)
        # The response is already parsed into FanficResponse model
        fanfic_response = completion.choices[0].message.parsed
        return fanfic_response
        
    except Exception as e:
        log.error(f"Failed to generate fanfic: {e}")
        return None