from dataclasses import dataclass
from typing import List, ClassVar
import json
from structlog import get_logger

log = get_logger(__name__)


@dataclass
class ThreadResponse:
    """Base class for thread responses"""
    story: str
    comments: List[str]
    comment_key: ClassVar[str]  # Will be set by subclasses

    @classmethod
    def from_json(cls, json_str: str) -> 'ThreadResponse':
        """Parse JSON response into a ThreadResponse object"""
        try:
            # Remove code block markers if present
            clean_json = json_str.strip().replace('```json', '').replace('```', '')
            data = json.loads(clean_json)
            return cls(
                story=data['story'],
                comments=data.get(cls.comment_key, [])
            )
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse JSON: {e}")
            raise
        except KeyError as e:
            log.error(f"Missing required field: {e}")
            raise


@dataclass
class BugurtResponse(ThreadResponse):
    """2ch-style thread response"""
    comment_key: ClassVar[str] = '2ch_comments'


@dataclass
class GreentextResponse(ThreadResponse):
    """4chan-style thread response"""
    comment_key: ClassVar[str] = '4ch_comments'
