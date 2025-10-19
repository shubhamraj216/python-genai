"""Video generation routes."""
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from auth.services import get_current_user, get_user_by_id, update_user_fields
from videos.models import GenerateVideoRequest, GenerateVideoResponse, GenerationMode
from videos.services import generate_video
from utils.usage import ensure_user_usage_fields, increment_user_usage, _utc_today_iso
from utils.logger import get_logger
from config import Config

logger = get_logger("videos")
router = APIRouter(tags=["videos"])


@router.post("/api/videos/generate", response_model=GenerateVideoResponse)
def generate_video_endpoint(
    req: GenerateVideoRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Generate video from prompt using Gemini Veo3.
    
    Accepts:
      GenerateVideoRequest with prompt, model, aspect_ratio, resolution, mode, and optional images/video
    
    Behavior:
      - Validate user authentication and usage limits
      - Call Gemini Veo3 API with persona integration
      - Save video file to videos directory
      - Increment usage after successful generation
      - Return video URL and metadata
    """
    logger.info(f"Video generation request from user {user['id']} - mode: {req.mode}, model: {req.model}")

    # Guest quota enforcement
    if user.get("is_guest"):
        quota = int(user.get("guest_quota", 0))
        if quota <= 0:
            raise HTTPException(status_code=403, detail="Guest quota exhausted")
        update_user_fields(user["id"], {"guest_quota": quota - 1})

    # Check daily usage BEFORE calling Gemini
    usr = get_user_by_id(user["id"])
    if not usr:
        raise HTTPException(status_code=401, detail="User not found")
    usr = ensure_user_usage_fields(usr)
    today = _utc_today_iso()
    usage_today = int(usr.get("usage_today_count", 0)) if usr.get("usage_today_date") == today else 0
    daily_limit = int(usr.get("daily_limit", Config.DEFAULT_DAILY_LIMIT))
    if usage_today >= daily_limit:
        raise HTTPException(status_code=403, detail="Daily usage limit reached")

    # Validate request based on mode
    if req.mode == GenerationMode.TEXT_TO_VIDEO and not req.prompt:
        raise HTTPException(status_code=400, detail="Prompt is required for text-to-video mode")
    
    if req.mode == GenerationMode.FRAMES_TO_VIDEO and not req.start_frame:
        raise HTTPException(status_code=400, detail="Start frame is required for frames-to-video mode")
    
    if req.mode == GenerationMode.REFERENCES_TO_VIDEO:
        if not req.reference_images and not req.style_image:
            raise HTTPException(status_code=400, detail="At least one reference image or style image is required for references-to-video mode")
    
    if req.mode == GenerationMode.EXTEND_VIDEO:
        if not req.input_video:
            raise HTTPException(status_code=400, detail="Input video is required for extend-video mode")
        # Force resolution to 720p for extend mode
        if req.resolution.value != "720p":
            logger.warning(f"Forcing resolution to 720p for extend mode (was {req.resolution.value})")
            req.resolution = "720p"

    # Convert request models to dict format for service layer
    start_frame_dict = None
    if req.start_frame:
        start_frame_dict = {
            "mime_type": req.start_frame.mime_type,
            "data": req.start_frame.data,
        }

    end_frame_dict = None
    if req.end_frame:
        end_frame_dict = {
            "mime_type": req.end_frame.mime_type,
            "data": req.end_frame.data,
        }

    reference_images_list = None
    if req.reference_images:
        reference_images_list = [
            {"mime_type": img.mime_type, "data": img.data}
            for img in req.reference_images
        ]

    style_image_dict = None
    if req.style_image:
        style_image_dict = {
            "mime_type": req.style_image.mime_type,
            "data": req.style_image.data,
        }

    input_video_dict = None
    if req.input_video:
        input_video_dict = {
            "uri": req.input_video.uri,
        }

    # Call video generation service
    try:
        logger.info(f"Starting video generation for user {user['id']}...")
        if req.avatar_id:
            logger.info(f"Using avatar {req.avatar_id} for character consistency")
        result = generate_video(
            prompt=req.prompt,
            model=req.model.value,
            aspect_ratio=req.aspect_ratio.value if req.aspect_ratio else None,
            resolution=req.resolution.value,
            mode=req.mode.value,
            owner_id=user["id"],
            start_frame=start_frame_dict,
            end_frame=end_frame_dict,
            is_looping=req.is_looping or False,
            reference_images=reference_images_list,
            style_image=style_image_dict,
            input_video=input_video_dict,
            avatar_id=req.avatar_id
        )
        video_url = result.video_url
        video_uri = result.video_uri
        message = result.content
        logger.info(f"Video generated successfully for user {user['id']}: {video_url}")
    except ValueError as e:
        # Validation errors (user-facing, clear messages)
        logger.warning(f"Video generation validation error for user {user['id']}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Server/API errors
        logger.error(f"Video generation failed for user {user['id']}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation error: {str(e)}")

    # Increment usage only after successful generation
    try:
        increment_user_usage(user["id"], delta=1)
    except HTTPException:
        # concurrent limit reached
        raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")

    return GenerateVideoResponse(
        video_url=video_url,
        video_uri=video_uri,
        message=message,
    )

