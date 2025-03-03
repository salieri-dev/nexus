"""Service for image generation using fal-ai."""

from typing import Dict, Any, List, Tuple, AsyncGenerator, Optional, Union
import asyncio
import os
import tempfile
from urllib.parse import urlparse

from pyrogram.types import InputMediaPhoto
from structlog import get_logger

from src.services.falai import FalAI
from .constants import DEFAULT_CONFIG
from .repository import ImagegenRepository, ImagegenModelRepository
from src.database.repository.requests_repository import RequestRepository

log = get_logger(__name__)


def process_image_results(result):
    """
    Process the image generation results from fal into a simplified list format.
    
    Args:
        result (dict): The result dictionary from the fal API call
    
    Returns:
        list: A list of dictionaries, each containing 'before' and 'after' image information
    """
    # Collect all images from all outputs
    before_images = []
    final_images = []
    
    # Flatten the structure and collect images in one pass
    for value in result['outputs'].values():
        if 'images' in value:
            for img in value['images']:
                if 'before_' in img['filename']:
                    before_images.append(img)
                elif 'final_' in img['filename']:
                    final_images.append(img)
    
    # Sort images by filename
    before_images.sort(key=lambda x: x['filename'])
    final_images.sort(key=lambda x: x['filename'])
    
    # Create pairs using list comprehension
    return [
        {
            'before': {'filename': b['filename'], 'url': b['url']},
            'after': {'filename': a['filename'], 'url': a['url']}
        }
        for b, a in zip(before_images, final_images)
    ]

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

        # Get image size dimensions
        image_size = config.get("image_size", DEFAULT_CONFIG["image_size"])
        width, height = 512, 512  # Default square
        
        # Only the three specified image sizes are supported
        if image_size == "square":
            width, height = 512, 512
        elif image_size == "portrait_4_3":
            width, height = 512, 768
        elif image_size == "landscape_4_3":
            width, height = 768, 512
        else:
            log.error("Unknown image size", image_size=image_size)
            # Fall back to default square size
            image_size = "square"
            width, height = 512, 512

        # Base payload
        payload = {
            "width": width,
            "height": height,
            "batch_size": 4,  # Default to 4 images
            "prompt": enhanced_prompt,
            "negative_prompt": config.get("negative_prompt", DEFAULT_CONFIG["negative_prompt"]),
            "seed": "",  # Empty string for random seed
            "steps": 30,  # Default value
            "cfg": 5,  # Default value
            "checkpoint_url": model_url,
            "sampler": "dpmpp_2m",  # Default sampler
        }

        # If loras are present, add lora parameters
        if loras:
            # Use the first lora (as per UI, only one lora can be selected)
            if loras[0].get("path"):
                payload["lora_url"] = loras[0]["path"]
                payload["lora_strength"] = loras[0].get("weight", 1.0)

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
        
        # Process the result using the process_image_results function
        try:
            # Use the process_image_results function to get the structured data
            log.info("Processing image results", handler=handler)
            processed_results = process_image_results(handler)
            log.info("Processed image results", count=len(processed_results))
            
            # Extract only the 'after' URLs as requested
            for result in processed_results:
                if 'after' in result and 'url' in result['after']:
                    images.append(result['after']['url'])
        except Exception as e:
            log.error(f"Error processing image results: {str(e)}")
            
            # Fallback to direct extraction if processing fails
            if "outputs" in handler:
                for output in handler["outputs"].values():
                    if "images" in output:
                        for image in output["images"]:
                            if "url" in image and "final_" in image.get("filename", ""):
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

            log.info("Generating images", payload=payload, user_id=user_id, prompt=prompt)
            
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

            # Determine which endpoint to use based on whether LoRAs are present
            endpoint = "comfy/htkg/text-2-image-lora" if "lora_url" in payload else "comfy/htkg/text-2-image"
            log.info(f"Using endpoint: {endpoint}")
            
            # Submit the job to fal-ai synchronously
            handler = await falai.generate_image_sync(endpoint, payload)
            
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

            log.info("Generating images", payload=payload, user_id=user_id, prompt=prompt)
            
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

            # Determine which endpoint to use based on whether LoRAs are present
            endpoint = "comfy/htkg/text-2-image-lora" if "lora_url" in payload else "comfy/htkg/text-2-image"
            log.info(f"Using endpoint: {endpoint}")
            
            # Submit the job to fal-ai and yield progress events
            async for event in falai.generate_image(endpoint, payload):
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
    async def download_image(url: str) -> str:
        """
        Download an image from a URL to a temporary file.

        Args:
            url: The URL of the image to download

        Returns:
            Path to the downloaded file
        """
        import httpx

        # Create a temporary directory if it doesn't exist
        temp_dir = os.path.join(tempfile.gettempdir(), "telegram_images")
        os.makedirs(temp_dir, exist_ok=True)

        # Extract filename from URL or generate a random one
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename or "." not in filename:
            filename = f"image_{hash(url)}.jpg"

        # Full path to save the file
        file_path = os.path.join(temp_dir, filename)

        # Download the file
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                
                # Save the file
                with open(file_path, "wb") as f:
                    f.write(response.content)
                
                log.info(f"Downloaded image from {url} to {file_path}")
                return file_path
        except Exception as e:
            log.error(f"Error downloading image from {url}: {str(e)}")
            raise

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
