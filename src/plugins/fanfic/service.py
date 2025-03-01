from datetime import datetime
from typing import Optional, Dict, Tuple, Any

from pydantic import BaseModel, Field
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from structlog import get_logger

from src.database.client import DatabaseClient
from src.database.repository.bot_config_repository import BotConfigRepository
from src.services.openrouter import OpenRouter
from src.services.falai import FalAI
from .constants import DEFAULT_TEMPERATURE, MAX_TOKENS, MAX_MESSAGE_LENGTH, MESSAGES
from .repository import FanficRepository

log = get_logger(__name__)


# Pydantic model for fanfic response
class FanficResponse(BaseModel):
    """Pydantic model for fanfic response"""

    title: str = Field(description="The title of the fanfiction (in Russian)")
    content: str = Field(description="The full text of the fanfiction (in Russian)")
    image_prompt: str = Field(description="Come up with image prompt for poster to describe the story that will be created with AI. Be highly detailed in appearances. It should be safe for work (SFW). (In English!)")
    danbooru_prompt: str = Field(
        description="Come up with image prompt with danbooru tags (example: score_9, score_8_up, score_8, sexy 18 year old girl, 1girl, mikasa ackerman, black hair, short hair, black eyes, perfect breasts, hard nipples, fishnet stockings, seductive eyes, naughty, shaped body, defined waist, perfectly round breasts, very small round, anus, spread ass, slim waist, toned tummy, round butt, perfect butt, thighs, prominent breasts, small tan lines, large teardrop shaped breasts, oily skin, tan lines reaching out to the viewer, wide hips, carefree, nudity, nipples, small pussy, sexy pose, classroom, slim waist, perfect details, shy, seductive, big breasts, standing, close up, bottom up, point of view, cinematic lighting, volumetric lighting, lace panties, camel toe, erect nipples, oily skin) for poster to describe the story that will be created with AI (In English!). Be highly detailed in appearances, actions, and emotions. The more detailed the better."
    )


class FanficService:
    """Service for fanfic generation and management"""

    @staticmethod
    def get_repository():
        """Get fanfic repository instance"""
        db_client = DatabaseClient.get_instance()
        return FanficRepository(db_client.client)

    @staticmethod
    def get_config_repository():
        """Get bot config repository instance"""
        db_client = DatabaseClient.get_instance()
        return BotConfigRepository(db_client)

    @staticmethod
    async def validate_topic(topic: str) -> Tuple[bool, Optional[str]]:
        """
        Validate the fanfic topic.

        Args:
            topic: The topic to validate

        Returns:
            Tuple containing:
            - Boolean indicating if the topic is valid
            - Error message if invalid, None otherwise
        """
        if not topic:
            return False, MESSAGES["MISSING_TOPIC"]

        if len(topic) < 3:
            return False, MESSAGES["TOPIC_TOO_SHORT"]

        return True, None

    @staticmethod
    async def generate_fanfic(topic: str) -> Optional[FanficResponse]:
        """
        Generate a fanfiction based on the given topic using OpenRouter API.

        Args:
            topic: The topic/theme for the fanfiction

        Returns:
            Optional[FanficResponse]: Pydantic model containing the title and content of the generated fanfiction,
                                    or None if generation failed
        """
        config_repo = FanficService.get_config_repository()

        # Get system prompt and model name from config
        system_prompt = await config_repo.get_plugin_config_value("fanfic", "FANFIC_SYSTEM_PROMPT")
        model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME", "anthropic/claude-3.5-sonnet:beta")

        open_router = OpenRouter().client

        # Create the completion request using Pydantic model
        completion = await open_router.beta.chat.completions.parse(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Создай фанфик на тему '{topic}'. Это должно быть в формате JSON обязательно по схеме что тебе предоставляю я. Не забудь предоставить текст для генерации ПОСТЕРА фанфики на английском языке. Добавь сюда так же заголовок фанфика, нейронная сеть сможет это отрисовать."},
            ],
            model=model_name,
            temperature=DEFAULT_TEMPERATURE,
            max_tokens=MAX_TOKENS,
            response_format=FanficResponse,
        )
        log.info(completion)

        # The response is already parsed into FanficResponse model
        fanfic_response = completion.choices[0].message.parsed
        return fanfic_response

    @staticmethod
    async def save_fanfic_to_db(topic: str, fanfic_response: FanficResponse, user_id: int, chat_id: int) -> str:
        """
        Save generated fanfic to the database.

        Args:
            topic: The topic of the fanfic
            fanfic_response: The generated fanfic response
            user_id: ID of the user who requested the fanfic
            chat_id: ID of the chat where the fanfic was requested

        Returns:
            str: ID of the saved fanfic record
        """
        repository = FanficService.get_repository()
        config_repo = FanficService.get_config_repository()

        # Get model name from config
        model_name = await config_repo.get_plugin_config_value("fanfic", "FANFIC_MODEL_NAME", "anthropic/claude-3.5-sonnet:beta")

        # Store fanfic data in database
        fanfic_record = {
            "user_id": user_id,
            "chat_id": chat_id,
            "topic": topic,
            "title": fanfic_response.title,
            "content": fanfic_response.content,
            "image_prompt": fanfic_response.image_prompt,
            "danbooru_image_prompt": fanfic_response.danbooru_prompt,
            "timestamp": datetime.utcnow(),
            "model": model_name,
            "temperature": DEFAULT_TEMPERATURE,
        }

        return await repository.save_fanfic(fanfic_record)

    @staticmethod
    async def generate_image_with_falai(fanfic_response: FanficResponse) -> Dict[str, Any]:
        """
        Generate an image for the fanfic using FalAI.

        Args:
            fanfic_response: The generated fanfic response containing the image prompt

        Returns:
            Dict containing the image generation result with URLs and metadata
        """
        # Get FalAI singleton instance
        falai = FalAI()

        # Prepare the payload for image generation
        payload = {"prompt": fanfic_response.image_prompt, "image_size": "landscape_4_3", "num_inference_steps": 28, "guidance_scale": 3.5, "num_images": 1, "enable_safety_checker": False, "output_format": "jpeg", "loras": []}

        log.info(f"Generating image with prompt: {fanfic_response.image_prompt}")

        try:
            # Generate the image using flux-lora model
            final_result = None
            async for event in falai.generate_image("fal-ai/flux-lora", payload):
                # Log progress events if needed
                if isinstance(event, dict) and "logs" in event:
                    log.info(f"Image generation progress: {event['logs']}")

                # Store the final result
                final_result = event

            log.info(f"Image generation result: {final_result}")
            return final_result
        except Exception as e:
            log.error(f"Error generating image: {str(e)}")
            return {"success": False, "error": str(e)}
