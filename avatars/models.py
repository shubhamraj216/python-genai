"""Pydantic models for avatar management."""
from typing import Optional
from pydantic import BaseModel, Field


class AvatarMetadata(BaseModel):
    """Avatar metadata model."""
    id: str = Field(..., description="Unique avatar identifier")
    owner_id: str = Field(..., description="User who owns this avatar")
    name: str = Field(..., description="User-friendly avatar name")
    file_path: str = Field(..., description="Relative file path to avatar image")
    url: str = Field(..., description="Public URL to access avatar image")
    mime_type: str = Field(..., description="Image MIME type")
    created_at: str = Field(..., description="ISO timestamp of creation")
    is_default: bool = Field(False, description="Whether this is the user's default avatar")


class AvatarUploadResponse(BaseModel):
    """Response model for avatar upload."""
    avatar_id: str = Field(..., description="Unique avatar identifier")
    name: str = Field(..., description="Avatar name")
    url: str = Field(..., description="URL to access the avatar")
    message: str = Field(..., description="Success message")


class AvatarListResponse(BaseModel):
    """Response model for listing avatars."""
    avatars: list[AvatarMetadata] = Field(..., description="List of user's avatars")
    count: int = Field(..., description="Total number of avatars")


class AvatarDeleteResponse(BaseModel):
    """Response model for avatar deletion."""
    avatar_id: str = Field(..., description="Deleted avatar ID")
    message: str = Field(..., description="Success message")

