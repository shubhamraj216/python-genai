"""Image generation Pydantic models."""
from typing import Optional
from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    avatar_id: Optional[str] = Field(None, description="Optional avatar ID for character consistency")

