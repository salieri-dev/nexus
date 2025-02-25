from typing import List
from pydantic import BaseModel, Field


class Theme(BaseModel):
    """Pydantic model for a theme in the summarization response"""
    messages_id: List[int] = Field(
        description="IDs of messages that correspond to this theme. There should be just 3-4 IDs indicating start of the discussion, middle of the discussion, and end of the discussion."
    )
    name: str = Field(
        description="The name of the theme represented as a short sentence."
    )
    emoji: str = Field(
        description="An emoji that summarizes the name of the theme."
    )
    key_takeaways: List[str] = Field(
        description="Key takeaways that summarize the important points of the theme and opinions of the active participants"
    )


class SummarizationResponse(BaseModel):
    """Pydantic model for summarization response"""
    themes: List[Theme] = Field(
        description="Summarized themes extracted from the chat logs."
    )