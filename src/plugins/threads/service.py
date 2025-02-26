from typing import Optional

from structlog import get_logger

from .generators import BugurtGenerator, GreentextGenerator
from .models import BugurtResponse, GreentextResponse

log = get_logger(__name__)


def generate_bugurt_image(bugurt_response: BugurtResponse) -> Optional[bytes]:
    """Generate thread image from bugurt AI response"""
    try:
        # Check if we got a string (JSON) instead of a Pydantic object
        if isinstance(bugurt_response, str):
            # Parse the JSON string into a Pydantic model
            bugurt_response = BugurtResponse.model_validate_json(bugurt_response)

        # Generate image
        generator = BugurtGenerator()
        image_bytes = generator.generate_image(bugurt_response.story, bugurt_response.comments)

        if not image_bytes:
            log.error("Failed to generate bugurt image")
            return None

        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate bugurt: {e}")
        return None


def generate_greentext_image(greentext_response: GreentextResponse) -> Optional[bytes]:
    """Generate thread image from greentext AI response"""
    try:
        # Check if we got a string (JSON) instead of a Pydantic object
        if isinstance(greentext_response, str):
            # Parse the JSON string into a Pydantic model
            greentext_response = GreentextResponse.model_validate_json(greentext_response)

        # Generate image
        generator = GreentextGenerator()
        image_bytes = generator.generate_image(greentext_response.story, greentext_response.comments)

        if not image_bytes:
            log.error("Failed to generate greentext image")
            return None

        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate greentext: {e}")
        return None
