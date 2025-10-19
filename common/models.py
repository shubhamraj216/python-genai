"""Unified generation models for multi-modal API."""
from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class UsageMetadata(BaseModel):
    """Token usage metadata from API response."""
    prompt_tokens: int = Field(0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(0, description="Number of tokens in the completion/response")
    total_tokens: int = Field(0, description="Total number of tokens used")


class CostInfo(BaseModel):
    """Cost information in USD."""
    prompt_cost: float = Field(0.0, description="Cost for prompt tokens in USD")
    completion_cost: float = Field(0.0, description="Cost for completion tokens in USD")
    total_cost: float = Field(0.0, description="Total cost for this request in USD")
    currency: str = Field("USD", description="Currency code")


class SessionCostInfo(BaseModel):
    """Cumulative session/conversation cost."""
    total_cost: float = Field(0.0, description="Total cumulative cost in USD")
    total_tokens: int = Field(0, description="Total cumulative tokens used")
    currency: str = Field("USD", description="Currency code")


class GenerationServiceResponse(BaseModel):
    """Common response structure for all generation services."""
    # Text content (always present)
    content: str = Field("", description="Generated text content or message")
    
    # Optional assets (for IMAGE/VIDEO modes)
    assets: Optional[List[Dict[str, Any]]] = Field(None, description="Generated assets (images/videos)")
    
    # Video-specific fields
    video_url: Optional[str] = Field(None, description="Video file URL")
    video_uri: Optional[str] = Field(None, description="Video URI for extension")
    
    # Usage tracking
    usage_metadata: Optional[Any] = Field(None, description="Raw usage metadata from API")


class GenerationMode(str, Enum):
    """Generation modes for unified endpoint."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    PLAN = "plan"
    AUTO = "auto"


class ImageInput(BaseModel):
    """Image input data matching Gemini format."""
    mime_type: str = Field(..., description="Image MIME type (e.g., image/png, image/jpeg)")
    data: str = Field(..., description="Base64-encoded image data")


class VideoData(BaseModel):
    """Video data for extend video mode."""
    uri: str = Field(..., description="Video URI from previous generation")


class VideoMode(str, Enum):
    """Video generation sub-modes."""
    TEXT_TO_VIDEO = "text_to_video"
    FRAMES_TO_VIDEO = "frames_to_video"
    REFERENCES_TO_VIDEO = "references_to_video"
    EXTEND_VIDEO = "extend_video"


class VeoModel(str, Enum):
    """Veo model variants."""
    # Veo 2.0 models
    VEO_2_0_001 = "veo-2.0-generate-001"
    
    # Veo 3.0 models
    VEO_3_0_001 = "veo-3.0-generate-001"
    VEO_3_0_FAST = "veo-3.0-fast-generate-001"
    
    # Veo 3.1 models
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


class SceneDefinition(BaseModel):
    """Definition of a single scene in a video generation plan."""
    id: str = Field(..., description="Unique scene identifier (e.g., 'scene_1')")
    description: str = Field(..., description="Original scene description from script")
    prompt: str = Field(..., description="Optimized prompt for video generation")
    mode: VideoMode = Field(..., description="Video generation mode for this scene")
    duration_hint: str = Field("5s", description="Suggested duration (e.g., '5s', '10s')")
    pre_generate_images: bool = Field(False, description="Whether to generate reference images first")
    image_prompts: Optional[List[str]] = Field(None, description="Prompts for pre-generating images")
    dependencies: List[str] = Field(default_factory=list, description="IDs of scenes this depends on")
    reasoning: str = Field("", description="Explanation of why this strategy was chosen")
    
    # Optional scene-specific settings
    aspect_ratio: Optional[AspectRatio] = Field(None, description="Override aspect ratio for this scene")
    resolution: Optional[Resolution] = Field(None, description="Override resolution for this scene")
    model: Optional[VeoModel] = Field(None, description="Override model for this scene")


class OrchestrationStrategy(BaseModel):
    """Strategy for executing scenes in parallel or sequentially."""
    parallel_groups: List[List[str]] = Field(
        default_factory=list,
        description="Groups of scene IDs that can run in parallel"
    )
    sequential_chains: List[List[str]] = Field(
        default_factory=list,
        description="Chains of scene IDs that must run sequentially"
    )


class VideoGenerationPlan(BaseModel):
    """Complete execution plan for script-based video generation."""
    scenes: List[SceneDefinition] = Field(..., description="List of scenes in execution order")
    orchestration: OrchestrationStrategy = Field(..., description="Execution orchestration strategy")
    overall_strategy: str = Field(..., description="Brief explanation of the overall approach")
    estimated_duration: Optional[str] = Field(None, description="Total estimated video duration")
    
    # Metadata
    created_at: Optional[str] = Field(None, description="Timestamp when plan was created")
    script_hash: Optional[str] = Field(None, description="Hash of original script for validation")


class SceneResult(BaseModel):
    """Result of executing a single scene."""
    scene_id: str = Field(..., description="Scene identifier")
    success: bool = Field(..., description="Whether generation succeeded")
    video_url: Optional[str] = Field(None, description="URL to generated video")
    video_uri: Optional[str] = Field(None, description="Gemini video URI for extending")
    generated_images: Optional[List[Dict[str, Any]]] = Field(None, description="Pre-generated reference images")
    error: Optional[str] = Field(None, description="Error message if failed")
    duration_seconds: Optional[float] = Field(None, description="Time taken to generate")
    cost: Optional[CostInfo] = Field(None, description="Cost for this scene")


class UnifiedGenerateRequest(BaseModel):
    """Unified request model for all generation modes."""
    # Core fields
    mode: GenerationMode = Field(..., description="Generation mode: text, image, video, plan, or auto")
    prompt: str = Field(..., description="Text prompt for generation")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID for history context")
    
    # Avatar for character consistency
    avatar_id: Optional[str] = Field(None, description="Optional avatar ID for character consistency across generations")
    
    # Image inputs (for all modes)
    images: Optional[List[ImageInput]] = Field(None, description="Optional images to include with the prompt")
    
    # Video-specific fields
    video_mode: Optional[VideoMode] = Field(VideoMode.TEXT_TO_VIDEO, description="Video generation sub-mode")
    model: Optional[VeoModel] = Field(VeoModel.VEO_FAST, description="Veo model to use for video generation")
    aspect_ratio: Optional[AspectRatio] = Field(AspectRatio.LANDSCAPE, description="Video aspect ratio")
    resolution: Optional[Resolution] = Field(Resolution.P720, description="Video resolution")
    
    # Frames to video mode
    start_frame: Optional[ImageInput] = Field(None, description="Starting frame for frames_to_video mode")
    end_frame: Optional[ImageInput] = Field(None, description="Ending frame for frames_to_video mode")
    is_looping: Optional[bool] = Field(False, description="Use start frame as end frame for looping")
    
    # References to video mode
    reference_images: Optional[List[ImageInput]] = Field(None, description="Reference images for asset-based generation")
    style_image: Optional[ImageInput] = Field(None, description="Style reference image")
    
    # Extend video mode
    input_video: Optional[VideoData] = Field(None, description="Input video to extend (requires video URI)")
    
    # Plan mode fields (use mode="plan")
    script: Optional[str] = Field(None, description="Narrative script for plan mode (used when creating plan)")
    execution_plan: Optional[VideoGenerationPlan] = Field(None, description="Execution plan for plan mode (used when executing plan)")


class UnifiedGenerateResponse(BaseModel):
    """Unified response model for all generation modes."""
    mode: GenerationMode = Field(..., description="The mode that was used for generation")
    conversation_id: str = Field(..., description="Conversation ID for this interaction")
    message: Dict[str, Any] = Field(..., description="The assistant message with content and optional assets")
    
    # Mode-specific fields (populated based on mode)
    text_response: Optional[str] = Field(None, description="Text response for TEXT mode")
    assets: Optional[List[Dict[str, Any]]] = Field(None, description="Generated assets for IMAGE mode")
    video_url: Optional[str] = Field(None, description="Video URL for VIDEO mode")
    video_uri: Optional[str] = Field(None, description="Video URI for extending (VIDEO mode)")
    
    # Auto mode metadata
    detected_mode: Optional[GenerationMode] = Field(None, description="The mode detected by AUTO classifier")
    
    # Plan mode fields
    plan_created: Optional[bool] = Field(None, description="Whether a plan was created (plan mode)")
    plan_executed: Optional[bool] = Field(None, description="Whether a plan was executed (plan mode)")
    execution_plan: Optional[VideoGenerationPlan] = Field(None, description="The created or executed plan")
    scene_results: Optional[List[SceneResult]] = Field(None, description="Results from executed scenes")
    estimated_cost: Optional[CostInfo] = Field(None, description="Estimated cost for plan execution")
    
    # Usage and cost tracking
    usage: Optional[UsageMetadata] = Field(None, description="Token usage for this request")
    cost: Optional[CostInfo] = Field(None, description="Cost for this request")
    session_cost: Optional[SessionCostInfo] = Field(None, description="Cumulative cost for this conversation")

