from typing import Optional

from pydantic import BaseModel, Field
from structlog import get_logger

from src.services.openrouter import OpenRouter

log = get_logger(__name__)

# Pydantic model for fanfic response
class FanficResponse(BaseModel):
    """Pydantic model for fanfic response"""
    title: str = Field(description="The title of the fanfiction")
    content: str = Field(description="The full text of the fanfiction")

# System prompt for fanfic generation
FANFIC_SYSTEM_PROMPT = """You are a creative writer specializing in fanfiction. 
Your task is to create an engaging, well-structured fanfiction based on the topic provided by the user.

Guidelines:
- Create a fanfiction of approximately 500-1000 words
- Include a title for the fanfiction
- Write in a narrative style with proper paragraphs
- Include dialogue where appropriate
- Be creative and entertaining
- Keep the content appropriate for general audiences
- Write in Russian language
"""


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
        open_router = OpenRouter().client
        
        # Create the completion request using Pydantic model
        completion = await open_router.beta.chat.completions.parse(
            messages=[
                {
                    "role": "system",
                    "content": FANFIC_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Создай фанфик на тему '{topic}'."
                }
            ],
            model="x-ai/grok-2-1212",
            temperature=0.8,
            max_tokens=4000,
            response_format=FanficResponse,
            seed=42
        )
        
        log.info(completion)
        # Extract the response content
        completion_response = completion.choices[0].message.content
        
        # Parse the response using Pydantic model
        fanfic_response = FanficResponse.model_validate_json(completion_response)
        return fanfic_response
        
    except Exception as e:
        log.error(f"Failed to generate fanfic: {e}")
        return None