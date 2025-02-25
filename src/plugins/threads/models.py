from typing import List

from pydantic import BaseModel, Field
from structlog import get_logger

log = get_logger(__name__)


class ThreadResponse(BaseModel):
    """Base class for thread responses"""
    story: str = Field(description="The thread story text")
    comments: List[str] = Field(description="Comments on the thread")


class BugurtResponse(ThreadResponse):
    """2ch-style thread response"""
    story: str = Field(description="The bugurt story with @ separators between lines")
    comments: List[str] = Field(
        description="Comments in 2ch style. They never have >> (double quotation marks). But they can have '>' quotation (single lesser than sign) when used to QUOTE what people saying.",
        min_items=2,
        max_items=4
    )


class GreentextResponse(ThreadResponse):
    """4chan-style thread response"""
    story: str = Field(description="The greentext story that is funny or sad in the style of typical 4chan user on /b/ board")
    comments: List[str] = Field(
        description="Comments in 4ch style on /b/ board",
        min_items=1,
        max_items=3
    )
