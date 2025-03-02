"""Service for image generation using fal-ai."""

from typing import Dict, Any, List, Tuple, AsyncGenerator, Optional, Union
import asyncio

from pyrogram.types import InputMediaPhoto
from structlog import get_logger

from src.services.falai import FalAI
from .constants import DEFAULT_CONFIG, AVAILABLE_SCHEDULERS
from .repository import ImagegenRepository, ImagegenModelRepository
from src.database.repository.requests_repository import RequestRepository

log = get_logger(__name__)


class ImagegenService:
    """Service for generating images using fal-ai."""

    # Repository instances cache
    _repositories = {}

    @staticmethod
    def get_repository(repo_type: str = "imagegen") -> Union[ImagegenRepository, ImagegenModelRepository, RequestRepository]:
        """
        Get repository instance by type.
        
        Args:
            repo_type: Type of repository to get ("imagegen", "model", or "request")
            
        Returns:
            Repository instance
        """
        if repo_type not in ImagegenService._repositories:
            if repo_type == "imagegen":
                ImagegenService._repositories[repo_type] = ImagegenRepository()
            elif repo_type == "model":
                ImagegenService._repositories[repo_type] = ImagegenModelRepository()
            elif repo_type == "request":
                ImagegenService._repositories[repo_type] = RequestRepository()
            else:
                raise ValueError(f"Unknown repository type: {repo_type}")
                
        return ImagegenService._repositories[repo_type]

    @staticmethod
    async def initialize():
        """Initialize the service by initializing the repositories."""
        # Initialize all repositories in parallel
        model_repo = ImagegenService.get_repository("model")
        request_repo = ImagegenService.get_repository("request")
        
        await asyncio.gather(
            model_repo.initialize(),
            request_repo.initialize()
        )

    @staticmethod
    async def _get_model_data(model_id: str, field: str = None) -> Union[Dict[str, Any], str]:
        """
        Get model data or a specific field from model ID.

        Args:
            model_id: The model ID to look up
            field: Optional specific field to return (e.g., "url", "preview_url")

        Returns:
            The model data dictionary or specific field value

        Raises:
            ValueError: If the model is not found
        """
        repo = ImagegenService.get_repository("model")
        model_data = await repo.get_model_by_id(model_id)

        if not model_data:
            log.error("Model not found", model_id=model_id)
            raise ValueError(f"Model not found: {model_id}")

        if field:
            if field not in model_data:
                log.error(f"Field {field} not found in model data", model_id=model_id)
                return "" if field == "preview_url" else None
            return model_data[field]
            
        return model_data

    @staticmethod
    async def _get_model_url(model_id: str) -> str:
        """
        Get model URL from model ID.

        Args:
            model_id: The model ID to look up

        Returns:
            The model URL

        Raises:
            ValueError: If the model is not found or URL is missing
        """
        url = await ImagegenService._get_model_data(model_id, "url")
        if not url:
            log.error("Model URL not found", model_id=model_id)
            raise ValueError(f"Model URL not found: {model_id}")
        return url
    
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
        return await ImagegenService._get_model_data(model_id, "preview_url") or ""

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
        repo = ImagegenService.get_repository("model")

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
                    "lora_id": lora_id,  # Store the original ID for later reference
                    "lora_name": lora_data.get("name", lora_id)  # Store the name for easier access
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
    async def _extract_image_urls(handler: Dict[str, Any]) -> List[str]:
        """
        Extract image URLs from the API response.

        Args:
            handler: The API response handler

        Returns:
            List of image URLs
        """
        images = []
        if "images" in handler:
            for image in handler["images"]:
                if "url" in image:
                    images.append(image["url"])

        log.info("Extracted image URLs", count=len(images))
        return images

    @staticmethod
    async def _create_request_record(
        req_type: str,
        user_id: int,
        chat_id: int,
        prompt: str,
        config: Dict[str, Any],
        payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create a request record in the database.
        
        Args:
            req_type: Type of request
            user_id: User ID
            chat_id: Chat ID
            prompt: Prompt text
            config: User configuration
            payload: API payload
            
        Returns:
            Created request document or None if creation failed
        """
        request_repo = ImagegenService.get_repository("request")
        return await request_repo.create_request(
            req_type=req_type,
            user_id=user_id,
            chat_id=chat_id,
            prompt=prompt,
            config=config,
            payload=payload,
            status="processing"
        )
        
    @staticmethod
    async def _update_request_record(
        request_doc: Dict[str, Any],
        image_urls: List[str] = None,
        error: str = None,
        status: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update a request record in the database.
        
        Args:
            request_doc: Request document to update
            image_urls: Image URLs to store
            error: Error message if any
            status: New status
            
        Returns:
            Updated request document or None if update failed
        """
        if not request_doc:
            return None
            
        request_repo = ImagegenService.get_repository("request")
        return await request_repo.update_request(
            str(request_doc["_id"]),
            image_urls=image_urls,
            error=error,
            status=status
        )

    @staticmethod
    async def on_queue_update(update: Dict[str, Any]):
        """
        Handle queue updates from fal-ai.

        Args:
            update: The queue update information
        """
        log.info("Queue update", position=update.get("position"), status=update.get("status"))

    @staticmethod
    async def _generate_images_sync(
        user_id: int,
        prompt: str,
        chat_id: int = None
    ) -> List[str]:
        """
        Internal method for generating images synchronously.
        
        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation
            chat_id: The chat ID where the request was made (defaults to user_id if not provided)
            
        Returns:
            List of image URLs
            
        Raises:
            Exception: If image generation fails
        """
        # If chat_id is not provided, use user_id as chat_id
        if chat_id is None:
            chat_id = user_id
            
        # Get user configuration
        config = await ImagegenRepository.get_imagegen_config(user_id)
        
        # Create request record with initial status
        request_doc = None
        image_urls = []
        
        try:
            # Prepare payload
            payload = await ImagegenService._prepare_generation_payload(user_id, prompt)

            log.info("Generating images", user_id=user_id, prompt=prompt)
            
            # Create a new request record with processing status
            request_doc = await ImagegenService._create_request_record(
                req_type="imagegen",
                user_id=user_id,
                chat_id=chat_id,
                prompt=prompt,
                config=config,
                payload=payload
            )

            # Get FalAI client
            falai = FalAI()

            # Submit the job to fal-ai synchronously
            handler = await falai.generate_image_sync("fal-ai/lora", payload)
            
            # Extract image URLs from the result
            image_urls = await ImagegenService._extract_image_urls(handler)
            
            # Update the existing request with success status and image URLs
            if request_doc and image_urls:
                await ImagegenService._update_request_record(
                    request_doc,
                    image_urls=image_urls,
                    status="success"
                )
                
            return image_urls

        except Exception as e:
            log.error("Error generating images", error=str(e), user_id=user_id, prompt=prompt)
            
            # Update the existing request with failure status and error message
            if request_doc:
                await ImagegenService._update_request_record(
                    request_doc,
                    error=str(e),
                    status="failure"
                )
                
            raise
            
    @staticmethod
    async def _generate_images_with_progress_internal(
        user_id: int,
        prompt: str,
        chat_id: int = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Internal method for generating images with progress updates.
        
        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation
            chat_id: The chat ID where the request was made (defaults to user_id if not provided)
            
        Yields:
            Dictionary with event information during generation
        """
        # If chat_id is not provided, use user_id as chat_id
        if chat_id is None:
            chat_id = user_id
            
        # Get user configuration
        config = await ImagegenRepository.get_imagegen_config(user_id)
        
        # Create request record with initial status
        request_doc = None
        image_urls = []
        
        try:
            # Prepare payload
            payload = await ImagegenService._prepare_generation_payload(user_id, prompt)

            log.info("Generating images with progress", user_id=user_id, prompt=prompt)
            
            # Create a new request record with processing status
            request_doc = await ImagegenService._create_request_record(
                req_type="imagegen",
                user_id=user_id,
                chat_id=chat_id,
                prompt=prompt,
                config=config,
                payload=payload
            )

            # Get FalAI client
            falai = FalAI()

            # Submit the job to fal-ai and yield progress events
            async for event in falai.generate_image("fal-ai/lora", payload):
                # Extract image URLs if available
                if "images" in event and event.get("images"):
                    image_urls = [img.get("url") for img in event.get("images") if img.get("url")]
                
                yield event

            # Update the existing request with success status and image URLs
            if request_doc and image_urls:
                await ImagegenService._update_request_record(
                    request_doc,
                    image_urls=image_urls,
                    status="success"
                )

        except Exception as e:
            log.error("Error generating images with progress", error=str(e), user_id=user_id, prompt=prompt)
            
            # Update the existing request with failure status and error message
            if request_doc:
                await ImagegenService._update_request_record(
                    request_doc,
                    error=str(e),
                    status="failure"
                )
                
            yield {"error": str(e)}

    @staticmethod
    async def generate_images(user_id: int, prompt: str, chat_id: int = None) -> List[str]:
        """
        Generate images based on the prompt and user configuration.

        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation
            chat_id: The chat ID where the request was made (defaults to user_id if not provided)

        Returns:
            List of URLs to the generated images

        Raises:
            Exception: If image generation fails
        """
        return await ImagegenService._generate_images_sync(
            user_id=user_id,
            prompt=prompt,
            chat_id=chat_id
        )

    @staticmethod
    async def generate_images_with_progress(user_id: int, prompt: str, chat_id: int = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate images with progress updates.

        Args:
            user_id: The user ID to get configuration for
            prompt: The prompt for image generation
            chat_id: The chat ID where the request was made (defaults to user_id if not provided)

        Yields:
            Dictionary with event information during generation
        """
        async for event in ImagegenService._generate_images_with_progress_internal(
            user_id=user_id,
            prompt=prompt,
            chat_id=chat_id
        ):
            yield event

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
