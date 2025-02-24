from typing import Optional

from structlog import get_logger

from .models import BugurtResponse, GreentextResponse
from .generators import BugurtGenerator, GreentextGenerator

log = get_logger(__name__)


def generate_bugurt_image(json_response: str) -> Optional[bytes]:
    """Generate thread image from bugurt AI response"""
    try:
        # Parse response
        bugurt = BugurtResponse.from_json(json_response)

        # Generate image
        generator = BugurtGenerator()
        image_bytes = generator.generate_image(bugurt.story, bugurt.comments)

        if not image_bytes:
            log.error("Failed to generate bugurt image")
            return None

        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate bugurt: {e}")
        return None


def generate_greentext_image(json_response: str) -> Optional[bytes]:
    """Generate thread image from greentext AI response"""
    try:
        # Parse response
        greentext = GreentextResponse.from_json(json_response)

        # Generate image
        generator = GreentextGenerator()
        image_bytes = generator.generate_image(greentext.story, greentext.comments)

        if not image_bytes:
            log.error("Failed to generate greentext image")
            return None

        return image_bytes

    except Exception as e:
        log.error(f"Failed to generate greentext: {e}")
        return None
