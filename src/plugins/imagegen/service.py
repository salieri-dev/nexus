"""Service for image generation using fal-ai."""

from typing import Dict, Any, List, Tuple, AsyncGenerator

from pyrogram.types import InputMediaPhoto
from structlog import get_logger

from src.services.falai import FalAI
from .constants import DEFAULT_CONFIG, AVAILABLE_SCHEDULERS
from .repository import ImagegenRepository, ImagegenModelRepository

log = get_logger(__name__)


class ImagegenService:
    """Service for generating images using fal-ai."""

    @staticmethod
    def get_repository():
        """Get imagegen repository instance"""
        return ImagegenRepository()

    @staticmethod
    def get_model_repository():
        """Get model repository instance"""
        return ImagegenModelRepository()

    @staticmethod
    async def initialize():
        """Initialize the service by initializing the model repository."""
        repo = ImagegenService.get_model_repository()
        await repo.initialize()

    @staticmethod
    async def _get_model_url(model_id: str) -> str:
        """
        Get model URL from model ID.

        Args:
            model_id: The model ID to look up

        Returns:
            The model URL

        Raises:
            ValueError: If the model is not found
        """
        repo = ImagegenService.get_model_repository()
        model_data = await repo.get_model_by_id(model_id)

        if not model_data or not model_data.get("url"):
            log.error("Model not found", model_id=model_id)
            raise ValueError(f"Model not found: {model_id}")

        return model_data["url"]
    
    @staticmethod
    async def _get_model_preview_url(model_id: str) -> str:
        """
        Get model preview URL from model ID.

        Args:
            model_id: The model ID to look up

        Returns:
            The model preview URL or empty string if not found

        Raises:
            ValueError: If the model is not found
        """
        repo = ImagegenService.get_model_repository()
        model_data = await repo.get_model_by_id(model_id)

        if not model_data:
            log.error("Model not found", model_id=model_id)
            raise ValueError(f"Model not found: {model_id}")

        return model_data.get("preview_url", "")

    @staticmethod
    async def _get_scheduler_display_name(scheduler_id: str) -> str:
        """
        Get scheduler display name from scheduler ID.

        Args:
            scheduler_id: The scheduler ID to look up

        Returns:
            The scheduler display name
        """
        # Find the display name for the scheduler ID
        for display_name, id_value in AVAILABLE_SCHEDULERS.items():
            if id_value == scheduler_id:
                return display_name

        # Default if not found
        log.warning("Scheduler not found, using default", scheduler_id=scheduler_id)
        return "DPM++ 2M SDE Karras"

    @staticmethod
    async def _enhance_prompt_with_trigger_words(prompt: str, trigger_words: List[str]) -> str:
        """
        Enhance prompt with trigger words.

        Args:
            prompt: The original prompt
            trigger_words: List of trigger words to add

        Returns:
            Enhanced prompt with trigger words
        """
        if not trigger_words:
            return prompt

        enhanced_prompt = f"{prompt}, {', '.join(trigger_words)}"
        log.info("Added trigger words to prompt", original=prompt, enhanced=enhanced_prompt)
        return enhanced_prompt

    @staticmethod
    async def _prepare_loras(lora_ids: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Prepare loras configuration for the API request.

        Args:
            lora_ids: List of lora IDs to include

        Returns:
            Tuple containing:
                - List of lora configurations for the API
                - List of trigger words to add to the prompt
        """
        if not lora_ids:
            log.info("No loras to prepare, returning empty lists")
            return [], []

        log.info("Preparing loras", lora_ids=lora_ids)
        repo = ImagegenService.get_model_repository()

        loras = []
        trigger_words = []

        for lora_id in lora_ids:
            log.info(f"Getting lora data for ID: {lora_id}")
            lora_data = await repo.get_lora_by_id(lora_id)
            if lora_data:
                log.info(f"Found lora data: {lora_data}")
                # Add lora configuration
                lora_config = {
                    "path": lora_data["url"],  # The API expects 'path' not 'model_name'
                    "weight": lora_data.get("default_scale", 0.7),  # Use default_scale from database
                }
                
                # Add preview_url if available
                if lora_data.get("preview_url"):
                    lora_config["preview_url"] = lora_data["preview_url"]
                    
                loras.append(lora_config)
                log.info(f"Added lora config: {lora_config}")

                # Collect trigger words if any
                if lora_data.get("trigger_words"):
                    trigger_words.append(lora_data["trigger_words"])
                    log.info(f"Added trigger words: {lora_data['trigger_words']}")
            else:
                log.warning(f"Lora with ID {lora_id} not found in database")

        log.info(f"Prepared {len(loras)} loras with {len(trigger_words)} trigger words")
        return loras, trigger_words

    @staticmethod
    async def _prepare_generation_payload(user_id: int, prompt: str) -> Dict[str, Any]:
        """
        Prepare the payload for image generation.

        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation

        Returns:
            Dictionary with the payload for the API request
        """
        # Get user configuration
        config = await ImagegenRepository.get_imagegen_config(user_id)
        
        log.info("Preparing generation payload", user_id=user_id, config=config)

        # Get model URL from ID
        model_id = config.get("model", DEFAULT_CONFIG["model"])
        model_url = await ImagegenService._get_model_url(model_id)

        # Prepare loras and get trigger words
        lora_ids = config.get("loras", [])
        log.info("Using loras", user_id=user_id, lora_ids=lora_ids)
        loras, trigger_words = await ImagegenService._prepare_loras(lora_ids)

        # Add trigger words to the prompt if any
        enhanced_prompt = await ImagegenService._enhance_prompt_with_trigger_words(prompt, trigger_words)

        # Get scheduler display name
        scheduler_id = config.get("scheduler", DEFAULT_CONFIG["scheduler"])
        scheduler_display_name = await ImagegenService._get_scheduler_display_name(scheduler_id)

        # Prepare payload
        payload = {
            "model_name": model_url,
            "prompt": enhanced_prompt,
            "negative_prompt": config.get("negative_prompt", DEFAULT_CONFIG["negative_prompt"]),
            "prompt_weighting": True,
            "loras": loras,
            "num_images": 4,  # Default to 4 images
            "image_size": config.get("image_size", DEFAULT_CONFIG["image_size"]),
            "num_inference_steps": 30,  # Default value
            "guidance_scale": config.get("cfg_scale", DEFAULT_CONFIG["cfg_scale"]),
            "clip_skip": 2,  # Default value
            "scheduler": scheduler_display_name,  # Use display name instead of ID
            "enable_safety_checker": False,
        }

        return payload

    @staticmethod
    async def _extract_image_urls(handler: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract image URLs and preview URLs from the API response.

        Args:
            handler: The API response handler

        Returns:
            List of dictionaries containing image URLs and preview URLs
        """
        images = []
        if "images" in handler:
            for image in handler["images"]:
                image_data = {}
                if "url" in image:
                    image_data["url"] = image["url"]
                    # Use the same URL as preview URL if not specified
                    image_data["preview_url"] = image.get("preview_url", image["url"])
                    images.append(image_data)

        log.info("Extracted image data", count=len(images))
        return [img["url"] for img in images]  # For backward compatibility, return just the URLs

    @staticmethod
    async def on_queue_update(update: Dict[str, Any]):
        """
        Handle queue updates from fal-ai.

        Args:
            update: The queue update information
        """
        log.info("Queue update", position=update.get("position"), status=update.get("status"))

    @staticmethod
    async def generate_images(user_id: int, prompt: str) -> List[str]:
        """
        Generate images based on the prompt and user configuration.

        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation

        Returns:
            List of URLs to the generated images

        Raises:
            Exception: If image generation fails
        """
        try:
            # Prepare payload
            payload = await ImagegenService._prepare_generation_payload(user_id, prompt)

            log.info("Generating images", user_id=user_id, prompt=prompt)

            # Get FalAI client
            falai = FalAI()

            # Submit the job to fal-ai
            handler = await falai.generate_image_sync("fal-ai/lora", payload)

            # Extract image URLs from the result
            return await ImagegenService._extract_image_urls(handler)

        except Exception as e:
            log.error("Error generating images", error=str(e), user_id=user_id, prompt=prompt)
            raise

    @staticmethod
    async def generate_images_with_progress(user_id: int, prompt: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate images with progress updates.

        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation

        Yields:
            Dictionary with event information during generation
        """
        try:
            # Prepare payload
            payload = await ImagegenService._prepare_generation_payload(user_id, prompt)

            log.info("Generating images with progress", user_id=user_id, prompt=prompt)

            # Get FalAI client
            falai = FalAI()

            # Submit the job to fal-ai and yield progress events
            async for event in falai.generate_image("fal-ai/lora", payload):
                yield event

        except Exception as e:
            log.error("Error generating images with progress", error=str(e), user_id=user_id, prompt=prompt)
            yield {"error": str(e)}

    @staticmethod
    async def create_media_group(image_urls: List[str], caption: str = None) -> List[InputMediaPhoto]:
        """
        Create a media group from image URLs.

        Args:
            image_urls: List of image URLs
            caption: Optional caption for the first image

        Returns:
            List of InputMediaPhoto objects for sending as a media group
        """
        media_group = []

        for i, url in enumerate(image_urls):
            # Add caption only to the first image
            media_caption = caption if i == 0 else None
            media_group.append(InputMediaPhoto(url, caption=media_caption))

        return media_group
