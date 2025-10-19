"""Video generation services - Gemini Veo3 integration."""
import os
import base64
import time
from typing import Optional, Dict, Any, List
from uuid import uuid4

from config import Config
from common.personas import get_active_persona
from common.models import GenerationServiceResponse
from utils.logger import get_logger
from videos.models import GenerationMode

logger = get_logger("videos.services")

# Gemini client
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


def save_video_file_return_url(file_name: str, data: bytes) -> str:
    """Save video file to videos directory and return URL."""
    path = os.path.join(Config.VIDEOS_DIR, file_name)
    with open(path, "wb") as f:
        f.write(data)
    # Return relative URL path (served by static mount)
    return f"/assets/generated/videos/{file_name}"


def generate_video(
    prompt: str,
    model: str,
    aspect_ratio: Optional[str],
    resolution: str,
    mode: str,
    owner_id: Optional[str] = None,
    start_frame: Optional[Dict[str, str]] = None,
    end_frame: Optional[Dict[str, str]] = None,
    is_looping: bool = False,
    reference_images: Optional[list] = None,
    style_image: Optional[Dict[str, str]] = None,
    input_video: Optional[Dict[str, str]] = None,
    input_images: Optional[List[Dict[str, str]]] = None,
    avatar_id: Optional[str] = None,
) -> GenerationServiceResponse:
    """
    Generate video using Gemini Veo3 API.
    
    Args:
        prompt: Text prompt for video generation
        model: Veo model identifier
        aspect_ratio: Video aspect ratio (16:9 or 9:16)
        resolution: Video resolution (720p or 1080p)
        mode: Generation mode (text_to_video, frames_to_video, etc.)
        owner_id: User ID for persona integration
        start_frame: Starting frame image data {mime_type, data}
        end_frame: Ending frame image data {mime_type, data}
        is_looping: Use start frame as end frame for looping
        reference_images: List of reference images
        style_image: Style reference image
        input_video: Input video for extension {uri}
        input_images: Optional additional images to include with prompt
                      Format: [{"mime_type": "...", "data": "base64..."}]
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        GenerationServiceResponse with content, video_url, video_uri, and usage_metadata
    """
    if genai is None or types is None:
        raise RuntimeError("genai client not available (google-genai not installed or import failed)")

    api_key = Config.get_gemini_api_key()
    client = genai.Client(api_key=api_key)

    logger.info(f"Starting video generation with mode: {mode}, model: {model}")
    
    # Check if model is veo-3.1 (required for frames_to_video and references_to_video)
    # Veo 2.0 and 3.0 only support basic text-to-video and extend-video modes
    is_veo_3_1 = "veo-3.1" in model.lower()
    
    # Validate mode compatibility with model
    if not is_veo_3_1:
        if mode == GenerationMode.FRAMES_TO_VIDEO.value:
            raise ValueError(
                "Frames-to-video mode is only supported with Veo 3.1 models. "
                "Please use 'veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview' model, "
                "or switch to text-to-video mode. (Current model: {})".format(model)
            )
        if mode == GenerationMode.REFERENCES_TO_VIDEO.value:
            raise ValueError(
                "References-to-video mode is only supported with Veo 3.1 models. "
                "Please use 'veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview' model, "
                "or switch to text-to-video mode. (Current model: {})".format(model)
            )
        if reference_images or style_image:
            raise ValueError(
                "Reference images are only supported with Veo 3.1 models. "
                "Please use 'veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview' model, "
                "or remove reference images. (Current model: {})".format(model)
            )
        if start_frame or end_frame:
            raise ValueError(
                "Start and end frames are only supported with Veo 3.1 models. "
                "Please use 'veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview' model, "
                "or remove frame parameters. (Current model: {})".format(model)
            )
        if avatar_id:
            raise ValueError(
                "Avatar consistency is only supported with Veo 3.1 models. "
                "Please use 'veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview' model, "
                "or remove the avatar parameter. (Current model: {})".format(model)
            )

    # Get active persona for system instruction (if owner_id provided)
    system_instruction_text = "You are a video-generation assistant."
    if owner_id:
        active_persona = get_active_persona(owner_id)
        if active_persona and active_persona.get("description"):
            system_instruction_text = active_persona["description"]
            logger.info(f"Using persona '{active_persona.get('name')}' (id: {active_persona.get('id')}) for user {owner_id}")
        else:
            logger.warning(f"No active persona found for user {owner_id}, using default system instruction")

    # Build generation config
    config = {
        "numberOfVideos": 1,
    }
    
    # Only add resolution for Veo 3.0+ models (not for Veo 2.0)
    if not model.startswith("veo-2.0"):
        config["resolution"] = resolution
        logger.info(f"Using resolution: {resolution}")
    else:
        logger.info(f"Skipping resolution for Veo 2.0 model: {model}")

    # Conditionally add aspect ratio (not used for extend video)
    if mode != GenerationMode.EXTEND_VIDEO.value:
        config["aspectRatio"] = aspect_ratio

    # Load and prepend avatar if provided (before building payload)
    avatar_instruction_added = False
    if avatar_id and owner_id:
        try:
            from avatars.services import load_avatar_as_base64
            avatar_image = load_avatar_as_base64(avatar_id, owner_id)
            logger.info(f"Using avatar {avatar_id} for video generation")
            
            # Add avatar to appropriate mode-specific parameters
            # For references_to_video mode, add to reference_images
            # For other modes, we can add to reference_images list which will be used below
            if mode == GenerationMode.REFERENCES_TO_VIDEO.value:
                if reference_images:
                    reference_images = [avatar_image] + reference_images
                else:
                    reference_images = [avatar_image]
                # Add consistency instruction to prompt
                if prompt:
                    prompt = f"Use this avatar consistently in your generations. {prompt}"
                else:
                    prompt = "Use this avatar consistently in your generations."
                avatar_instruction_added = True
            elif mode == GenerationMode.TEXT_TO_VIDEO.value:
                # For text-to-video with avatar, convert to references_to_video mode
                # This ensures the avatar image is actually sent to the API
                mode = GenerationMode.REFERENCES_TO_VIDEO.value
                logger.info(f"Converting TEXT_TO_VIDEO to REFERENCES_TO_VIDEO mode due to avatar presence")
                if reference_images:
                    reference_images = [avatar_image] + reference_images
                else:
                    reference_images = [avatar_image]
                # Add consistency instruction to prompt
                if prompt:
                    prompt = f"Use this avatar consistently in your generations. {prompt}"
                else:
                    prompt = "Use this avatar consistently in your generations."
                avatar_instruction_added = True
            elif mode == GenerationMode.FRAMES_TO_VIDEO.value:
                # For frames-to-video, if no start_frame provided, use avatar as start_frame
                if not start_frame:
                    start_frame = avatar_image
                    logger.info("Using avatar as start frame for frames_to_video mode")
                    # Add consistency instruction to prompt
                    if prompt:
                        prompt = f"Use this avatar consistently in your generations. {prompt}"
                    else:
                        prompt = "Use this avatar consistently in your generations."
                    avatar_instruction_added = True
            # For extend_video mode, avatar is not applicable
            
            if avatar_instruction_added:
                logger.info("Added avatar consistency instruction to prompt")
        except Exception as e:
            logger.warning(f"Failed to load avatar {avatar_id}: {e}")
            # Continue without avatar (optional parameter)
    
    # If TEXT_TO_VIDEO mode has reference_images (but no avatar), also convert to REFERENCES_TO_VIDEO
    # This ensures reference images are actually passed to the API
    if mode == GenerationMode.TEXT_TO_VIDEO.value and reference_images:
        mode = GenerationMode.REFERENCES_TO_VIDEO.value
        logger.info(f"Converting TEXT_TO_VIDEO to REFERENCES_TO_VIDEO mode due to reference images presence")
        # Add instruction to prompt
        if prompt:
            prompt = f"Use the provided reference images. {prompt}"
        else:
            prompt = "Use the provided reference images."
    
    # Build generate video payload
    generate_video_payload = {
        "model": model,
        "config": config,
    }

    # Add prompt if provided (and not empty) - after avatar instruction has been added
    if prompt:
        generate_video_payload["prompt"] = prompt
    
    # Log if input_images are provided (note: video API handles images via mode-specific params)
    if input_images:
        logger.info(f"Received {len(input_images)} input images (will be handled via mode-specific parameters)")

    # Handle different generation modes
    if mode == GenerationMode.FRAMES_TO_VIDEO.value:
        if start_frame:
            # Decode base64 data
            image_bytes = base64.b64decode(start_frame["data"])
            generate_video_payload["image"] = {
                "imageBytes": image_bytes,
                "mimeType": start_frame["mime_type"],
            }
            logger.info(f"Added start frame with mime type: {start_frame['mime_type']}")

        # Handle looping or end frame
        final_end_frame = start_frame if is_looping else end_frame
        if final_end_frame:
            end_image_bytes = base64.b64decode(final_end_frame["data"])
            generate_video_payload["config"]["lastFrame"] = {
                "imageBytes": end_image_bytes,
                "mimeType": final_end_frame["mime_type"],
            }
            if is_looping:
                logger.info("Generating looping video using start frame as end frame")
            else:
                logger.info(f"Added end frame with mime type: {final_end_frame['mime_type']}")

    elif mode == GenerationMode.REFERENCES_TO_VIDEO.value:
        reference_images_payload = []

        if reference_images:
            for img in reference_images:
                image_bytes = base64.b64decode(img["data"])
                reference_images_payload.append({
                    "image": {
                        "imageBytes": image_bytes,
                        "mimeType": img["mime_type"],
                    },
                    "referenceType": "ASSET",
                })
                logger.info(f"Added reference image with mime type: {img['mime_type']}")

        if style_image:
            style_bytes = base64.b64decode(style_image["data"])
            reference_images_payload.append({
                "image": {
                    "imageBytes": style_bytes,
                    "mimeType": style_image["mime_type"],
                },
                "referenceType": "STYLE",
            })
            logger.info(f"Added style image with mime type: {style_image['mime_type']}")

        if reference_images_payload:
            generate_video_payload["config"]["referenceImages"] = reference_images_payload

    elif mode == GenerationMode.EXTEND_VIDEO.value:
        if not input_video or not input_video.get("uri"):
            raise ValueError("Input video URI is required for extend video mode")
        
        # Create a Video object from URI
        video_obj = types.Video(uri=input_video["uri"])
        generate_video_payload["video"] = video_obj
        logger.info(f"Extending video from URI: {input_video['uri']}")

    logger.info("Submitting video generation request to Gemini...")
    logger.debug(f"Payload config: model={model}, resolution={resolution}, aspect_ratio={aspect_ratio}, mode={mode}")

    # Start video generation
    try:
        operation = client.models.generate_videos(**generate_video_payload)
        logger.info(f"Video generation operation started: {operation.name if hasattr(operation, 'name') else 'unknown'}")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Video generation request failed: {error_msg}")
        
        # Handle specific API validation errors with helpful messages
        if "INVALID_ARGUMENT" in error_msg or "400" in error_msg:
            if "referenceImages" in error_msg:
                raise ValueError(
                    "Reference images are not supported by this model. "
                    "Please use a Veo 3.1 model ('veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview'), "
                    "or switch to text-to-video mode without reference images."
                )
            elif "lastFrame" in error_msg or "frame" in error_msg.lower():
                raise ValueError(
                    "Start/end frames are not supported by this model. "
                    "Please use a Veo 3.1 model ('veo-3.1-fast-generate-preview' or 'veo-3.1-generate-preview'), "
                    "or switch to text-to-video mode without frames."
                )
            elif "Resolution of the input video must be 720p" in error_msg:
                raise ValueError("Video extension requires input video to be 720p resolution. Please use a 720p video or generate a new video instead.")
            elif "Resolution" in error_msg or "resolution" in error_msg:
                raise ValueError(f"Invalid resolution configuration: {error_msg}")
            else:
                raise ValueError(f"Invalid video generation parameters: {error_msg}")
        elif "rate" in error_msg.lower() or "quota" in error_msg.lower():
            raise RuntimeError("API rate limit exceeded. Please try again in a few minutes.")
        else:
            raise RuntimeError(f"Video generation failed: {error_msg}")

    # Poll for completion
    poll_count = 0
    while not operation.done:
        poll_count += 1
        time.sleep(10)  # Wait 10 seconds between polls
        logger.info(f"...Generating... (poll #{poll_count})")
        operation = client.operations.get(operation)

    logger.info(f"Video generation completed after {poll_count} polls")

    # Check for result
    if not operation.result:
        logger.error("Operation completed but no result found")
        raise RuntimeError("No result from video generation operation")

    generated_videos = operation.result.generated_videos

    if not generated_videos or len(generated_videos) == 0:
        logger.error("No videos were generated")
        raise RuntimeError("No videos were generated")

    first_video = generated_videos[0]
    if not first_video.video or not first_video.video.uri:
        logger.error("Generated video is missing a URI")
        raise RuntimeError("Generated video is missing a URI")

    video_object = first_video.video
    video_uri = video_object.uri

    logger.info(f"Video generated successfully with URI: {video_uri}")

    # Fetch the video file
    fetch_url = f"{video_uri}&key={api_key}"
    logger.info(f"Fetching video from Gemini...")

    # Use requests or httpx to fetch the video
    try:
        import httpx
        with httpx.Client(timeout=300.0, follow_redirects=True) as http_client:  # 5 minute timeout for large videos
            response = http_client.get(fetch_url)
            response.raise_for_status()
            video_bytes = response.content
    except ImportError:
        # Fallback to urllib if httpx not available
        import urllib.request
        # urllib.request.urlopen follows redirects by default
        with urllib.request.urlopen(fetch_url) as response:
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch video: {response.status}")
            video_bytes = response.read()

    logger.info(f"Fetched video: {len(video_bytes)} bytes")

    # Save video file
    video_id = str(uuid4())
    file_extension = ".mp4"  # Default to mp4 for videos
    filename = f"{video_id}{file_extension}"
    video_url = save_video_file_return_url(filename, video_bytes)

    logger.info(f"Saved video to: {video_url}")

    message = f"Video generated successfully using {mode} mode"
    if prompt:
        message += f" with prompt: '{prompt[:50]}...'"
    
    # Video API doesn't provide token-based usage metadata
    # Cost will be calculated as fixed per-video cost
    usage_metadata = None

    return GenerationServiceResponse(
        content=message,
        video_url=video_url,
        video_uri=video_uri,
        usage_metadata=usage_metadata
    )

