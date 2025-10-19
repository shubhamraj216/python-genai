"""Video generation Pydantic models."""
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class VeoModel(str, Enum):
    """Veo model variants."""
    # Veo 2.0 models (limited features: text-to-video only)
    VEO_2_0_001 = "veo-2.0-generate-001"
    
    # Veo 3.0 models (limited features: text-to-video only)
    VEO_3_0_001 = "veo-3.0-generate-001"
    VEO_3_0_FAST = "veo-3.0-fast-generate-001"
    
    # Veo 3.1 models (full features: all modes supported)
    VEO_FAST = "veo-3.1-fast-generate-preview"
    VEO = "veo-3.1-generate-preview"


class AspectRatio(str, Enum):
    """Video aspect ratios."""
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"


class Resolution(str, Enum):
    """Video resolutions."""
    P720 = "720p"
    P1080 = "1080p"


class GenerationMode(str, Enum):
    """Video generation modes."""
    TEXT_TO_VIDEO = "text_to_video"
    FRAMES_TO_VIDEO = "frames_to_video"
    REFERENCES_TO_VIDEO = "references_to_video"
    EXTEND_VIDEO = "extend_video"


class ImageData(BaseModel):
    """Image data for frame-based or reference-based generation."""
    mime_type: str = Field(..., description="Image MIME type (e.g., image/png, image/jpeg)")
    data: str = Field(..., description="Base64-encoded image data")


class VideoData(BaseModel):
    """Video data for extend video mode."""
    uri: str = Field(..., description="Video URI from previous generation")


class GenerateVideoRequest(BaseModel):
    """Request model for video generation."""
    prompt: str = Field("", description="Text prompt for video generation")
    model: VeoModel = Field(VeoModel.VEO_FAST, description="Veo model to use")
    aspect_ratio: Optional[AspectRatio] = Field(AspectRatio.LANDSCAPE, description="Video aspect ratio (not used for extend mode)")
    resolution: Resolution = Field(Resolution.P720, description="Video resolution")
    mode: GenerationMode = Field(GenerationMode.TEXT_TO_VIDEO, description="Generation mode")
    avatar_id: Optional[str] = Field(None, description="Optional avatar ID for character consistency")
    
    # Frames to video mode
    start_frame: Optional[ImageData] = Field(None, description="Starting frame image")
    end_frame: Optional[ImageData] = Field(None, description="Ending frame image")
    is_looping: Optional[bool] = Field(False, description="Use start frame as end frame for looping")
    
    # References to video mode
    reference_images: Optional[List[ImageData]] = Field(None, description="Reference images for asset-based generation")
    style_image: Optional[ImageData] = Field(None, description="Style reference image")
    
    # Extend video mode
    input_video: Optional[VideoData] = Field(None, description="Input video to extend")


class GenerateVideoResponse(BaseModel):
    """Response model for video generation."""
    video_url: str = Field(..., description="URL to access the generated video")
    video_uri: str = Field(..., description="Gemini video URI for extending")
    message: str = Field(..., description="Status message")

