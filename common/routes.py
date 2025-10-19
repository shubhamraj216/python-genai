"""Unified generation endpoint supporting text, image, video, and auto modes."""
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends
from zoneinfo import ZoneInfo

from auth.services import get_current_user, get_user_by_id, update_user_fields
from common.models import (
    UnifiedGenerateRequest, 
    UnifiedGenerateResponse, 
    GenerationMode,
    VideoMode,
    UsageMetadata
)
from common.text_service import generate_text
from common.classifier import classify_generation_mode
from common.cost_service import (
    extract_usage_from_gemini_response,
    calculate_cost_from_usage,
    calculate_video_cost,
    get_conversation_cost,
    add_cost_to_conversation as calculate_new_cost
)
from common.plan_service import create_plan_from_script, validate_plan, estimate_plan_cost
from common.plan_orchestrator import execute_plan
from image.services import call_gemini_generate_stream_and_save
from videos.services import generate_video
from conversations.services import (
    create_conversation,
    get_conversation,
    append_message_to_conversation,
    update_conversation_cost
)
from utils.usage import ensure_user_usage_fields, increment_user_usage, _utc_today_iso
from utils.logger import get_logger
from config import Config

logger = get_logger("unified")
router = APIRouter(tags=["unified"])


@router.post("/api/generate-unified", response_model=UnifiedGenerateResponse)
def generate_unified(
    req: UnifiedGenerateRequest,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Unified generation endpoint supporting multiple modes.
    
    Modes:
    - TEXT: Pure text generation/conversation
    - IMAGE: Image generation with optional text
    - VIDEO: Video generation with various sub-modes
    - PLAN: Script-based multi-scene video planning and execution
    - AUTO: Automatically detect intent and route to appropriate mode
    
    Supports:
    - Conversation history across all modes
    - Image inputs for all modes
    - Video-specific features (frames, references, extension)
    - Plan mode: script parsing, intelligent orchestration, parallel/sequential execution
    """
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")
    
    logger.info(f"Unified generation request from user {user['id']} - mode: {req.mode}")
    if req.avatar_id:
        logger.info(f"Using avatar {req.avatar_id} for character consistency")
    
    # Guest quota enforcement
    if user.get("is_guest"):
        quota = int(user.get("guest_quota", 0))
        if quota <= 0:
            raise HTTPException(status_code=403, detail="Guest quota exhausted")
        update_user_fields(user["id"], {"guest_quota": quota - 1})
    
    # Check daily usage BEFORE generation
    usr = get_user_by_id(user["id"])
    if not usr:
        raise HTTPException(status_code=401, detail="User not found")
    usr = ensure_user_usage_fields(usr)
    today = _utc_today_iso()
    usage_today = int(usr.get("usage_today_count", 0)) if usr.get("usage_today_date") == today else 0
    daily_limit = int(usr.get("daily_limit", Config.DEFAULT_DAILY_LIMIT))
    if usage_today >= daily_limit:
        raise HTTPException(status_code=403, detail="Daily usage limit reached")
    
    # Prepare conversation: use provided conv id or create one
    conv_id = req.conversation_id
    if conv_id:
        # Fetch existing conversation and verify ownership
        try:
            conv = get_conversation(conv_id, owner_id=user["id"])
        except KeyError:
            raise HTTPException(status_code=404, detail="conversation not found")
    else:
        # Create new conversation
        now_ist = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Kolkata"))
        title = f"Chat {now_ist.strftime('%b %d, %Y %I:%M %p IST')}"
        conv = create_conversation(owner_id=user["id"], title=title)
        conv_id = conv["id"]
    
    # Extract conversation history
    conversation_history = conv.get("messages", [])
    logger.info(f"Using conversation {conv_id} with {len(conversation_history)} existing messages")
    
    # ============================================================
    # PLAN MODE HANDLING
    # ============================================================
    if req.mode == GenerationMode.PLAN:
        logger.info("Plan mode activated")
        
        # Case 1: Creating a new plan from script
        if req.script and not req.execution_plan:
            logger.info("Creating new execution plan from script")
            
            if not req.script.strip():
                raise HTTPException(status_code=400, detail="Script cannot be empty in plan mode")
            
            try:
                # Create plan using AI
                plan = create_plan_from_script(req.script)
                
                # Validate plan
                validate_plan(plan)
                
                # Estimate cost
                estimated_cost = estimate_plan_cost(plan)
                
                logger.info(f"Plan created successfully: {len(plan.scenes)} scenes, estimated cost: ${estimated_cost.total_cost:.2f}")
                
                # Build user message for plan creation
                user_msg = {
                    "id": str(uuid4()),
                    "role": "user",
                    "content": f"Create video plan for script: {req.script[:100]}...",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                
                # Build assistant message
                plan_summary = f"I've created an execution plan with {len(plan.scenes)} scenes. {plan.overall_strategy}"
                assistant_msg = {
                    "id": str(uuid4()),
                    "role": "assistant",
                    "content": plan_summary,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "execution_plan": plan.dict(),  # Store plan in conversation history
                }
                
                # Append messages
                try:
                    append_message_to_conversation(conv_id, user_msg, owner_id=user["id"])
                    append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
                except KeyError:
                    logger.warning(f"Failed to append messages to conversation {conv_id}")
                
                # Return plan to user for review/editing
                return UnifiedGenerateResponse(
                    mode=GenerationMode.PLAN,
                    conversation_id=conv_id,
                    message=assistant_msg,
                    text_response=plan_summary,
                    plan_created=True,
                    execution_plan=plan,
                    estimated_cost=estimated_cost,
                    usage=None,
                    cost=None,
                    session_cost=None
                )
                
            except ValueError as e:
                logger.error(f"Plan creation validation error: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid script or plan: {str(e)}")
            except RuntimeError as e:
                logger.error(f"Plan creation runtime error: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create plan: {str(e)}")
        
        # Case 2: Executing an existing plan
        elif req.execution_plan:
            logger.info("Executing provided plan")
            
            try:
                # Validate plan
                validate_plan(req.execution_plan)
                
                # Check scene limit
                if len(req.execution_plan.scenes) > Config.PLAN_MAX_SCENES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Plan exceeds maximum allowed scenes ({Config.PLAN_MAX_SCENES})"
                    )
                
                # Execute plan
                logger.info(f"Executing plan with {len(req.execution_plan.scenes)} scenes")
                scene_results = execute_plan(
                    plan=req.execution_plan,
                    owner_id=user["id"],
                    default_aspect_ratio=req.aspect_ratio.value if req.aspect_ratio else "16:9",
                    default_resolution=req.resolution.value if req.resolution else "720p",
                    default_model=req.model.value if req.model else "veo-3.1-fast-generate-preview",
                    max_parallel_workers=Config.PLAN_MAX_PARALLEL_WORKERS,
                    avatar_id=req.avatar_id
                )
                
                # Calculate total cost
                total_cost = 0.0
                for result in scene_results:
                    if result.cost:
                        total_cost += result.cost.total_cost
                
                from common.models import CostInfo
                cost = CostInfo(
                    prompt_cost=0.0,
                    completion_cost=total_cost,
                    total_cost=total_cost,
                    currency="USD"
                )
                
                # Update conversation cost
                conv_updated = get_conversation(conv_id, owner_id=user["id"])
                new_total_cost, new_total_tokens = calculate_new_cost(None, cost, conv_updated)
                update_conversation_cost(conv_id, new_total_cost, new_total_tokens, owner_id=user["id"])
                session_cost = get_conversation_cost({"total_cost": new_total_cost, "total_tokens": new_total_tokens})
                
                # Build user message
                user_msg = {
                    "id": str(uuid4()),
                    "role": "user",
                    "content": f"Execute video plan with {len(req.execution_plan.scenes)} scenes",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                
                # Build summary
                success_count = sum(1 for r in scene_results if r.success)
                failure_count = len(scene_results) - success_count
                
                # Collect video assets from successful scenes
                video_assets = []
                for result in scene_results:
                    if result.success and result.video_url:
                        from assets.services import add_asset_metadata
                        video_asset_id = str(uuid4())
                        scene_def = next((s for s in req.execution_plan.scenes if s.id == result.scene_id), None)
                        scene_prompt = scene_def.prompt if scene_def else "Scene video"
                        add_asset_metadata(video_asset_id, "video", result.video_url, scene_prompt, owner_id=user["id"])
                        
                        video_assets.append({
                            "id": video_asset_id,
                            "type": "video",
                            "url": result.video_url,
                            "uri": result.video_uri,
                            "scene_id": result.scene_id,
                            "prompt": scene_prompt
                        })
                
                plan_summary = f"Plan execution completed: {success_count} scenes succeeded"
                if failure_count > 0:
                    plan_summary += f", {failure_count} scenes failed"
                
                # Build assistant message
                assistant_msg = {
                    "id": str(uuid4()),
                    "role": "assistant",
                    "content": plan_summary,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "assets": video_assets,
                    "execution_plan": req.execution_plan.dict(),  # Store plan in conversation history
                    "scene_results": [r.dict() for r in scene_results],  # Store results in conversation history
                }
                
                # Append messages
                try:
                    append_message_to_conversation(conv_id, user_msg, owner_id=user["id"])
                    append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
                except KeyError:
                    logger.warning(f"Failed to append messages to conversation {conv_id}")
                
                # Increment usage (count as one generation even if multiple scenes)
                try:
                    increment_user_usage(user["id"], delta=1)
                except HTTPException:
                    raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")
                
                # Return results
                return UnifiedGenerateResponse(
                    mode=GenerationMode.PLAN,
                    conversation_id=conv_id,
                    message=assistant_msg,
                    text_response=plan_summary,
                    plan_executed=True,
                    execution_plan=req.execution_plan,
                    scene_results=scene_results,
                    assets=video_assets,
                    usage=None,
                    cost=cost,
                    session_cost=session_cost
                )
                
            except ValueError as e:
                logger.error(f"Plan execution validation error: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid plan: {str(e)}")
            except RuntimeError as e:
                logger.error(f"Plan execution runtime error: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to execute plan: {str(e)}")
        
        else:
            raise HTTPException(
                status_code=400,
                detail="Plan mode (mode='plan') requires either 'script' (to create plan) or 'execution_plan' (to execute plan)"
            )
    
    # ============================================================
    # NORMAL GENERATION MODE (non-plan)
    # ============================================================
    
    # Build and append the user message first (persist immediately)
    user_msg = {
        "id": str(uuid4()),
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    # Add images to user message if provided
    if req.images:
        user_msg["images"] = [{"mime_type": img.mime_type, "data": img.data[:50] + "..."} for img in req.images]
        logger.info(f"User message includes {len(req.images)} image(s)")
    
    try:
        append_message_to_conversation(conv_id, user_msg, owner_id=user["id"])
    except KeyError:
        raise HTTPException(status_code=500, detail="failed to append user message to conversation")
    
    # Convert input images to dict format for services
    input_images = None
    if req.images:
        input_images = [{"mime_type": img.mime_type, "data": img.data} for img in req.images]
    
    # Determine actual mode (handle AUTO)
    actual_mode = req.mode
    detected_mode = None
    
    if req.mode == GenerationMode.AUTO:
        logger.info("AUTO mode detected, classifying intent...")
        actual_mode = classify_generation_mode(prompt, conversation_history)
        detected_mode = actual_mode
        logger.info(f"AUTO mode classified as: {actual_mode}")
    
    # Route to appropriate generation handler
    try:
        if actual_mode == GenerationMode.TEXT:
            logger.info("Routing to TEXT generation")
            result = generate_text(
                prompt=prompt,
                owner_id=user["id"],
                conversation_history=conversation_history,
                input_images=input_images,
                avatar_id=req.avatar_id
            )
            
            assistant_text = result.content
            usage_metadata_raw = result.usage_metadata
            
            # Extract usage and calculate cost
            usage = extract_usage_from_gemini_response(usage_metadata_raw) if usage_metadata_raw else None
            cost = calculate_cost_from_usage(usage) if usage else None
            
            # Get and update conversation cost
            conv_updated = get_conversation(conv_id, owner_id=user["id"])
            new_total_cost, new_total_tokens = calculate_new_cost(usage, cost, conv_updated)
            update_conversation_cost(conv_id, new_total_cost, new_total_tokens, owner_id=user["id"])
            session_cost = get_conversation_cost({"total_cost": new_total_cost, "total_tokens": new_total_tokens})
            
            # Build assistant message
            assistant_msg = {
                "id": str(uuid4()),
                "role": "assistant",
                "content": assistant_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            # Append to conversation
            try:
                append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
            except KeyError:
                logger.warning(f"Failed to append assistant message to conversation {conv_id}")
            
            # Increment usage
            try:
                increment_user_usage(user["id"], delta=1)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")
            
            return UnifiedGenerateResponse(
                mode=actual_mode,
                conversation_id=conv_id,
                message=assistant_msg,
                text_response=assistant_text,
                detected_mode=detected_mode,
                usage=usage,
                cost=cost,
                session_cost=session_cost
            )
        
        elif actual_mode == GenerationMode.IMAGE:
            logger.info("Routing to IMAGE generation")
            result = call_gemini_generate_stream_and_save(
                prompt=prompt,
                owner_id=user["id"],
                conversation_history=conversation_history,
                input_images=input_images,
                avatar_id=req.avatar_id
            )
            
            assistant_text = result.content if result.content else f"I've created images based on your prompt: \"{prompt}\"."
            saved_assets = result.assets or []
            usage_metadata_raw = result.usage_metadata
            
            # Extract usage and calculate cost
            usage = extract_usage_from_gemini_response(usage_metadata_raw) if usage_metadata_raw else None
            cost = calculate_cost_from_usage(usage) if usage else None
            
            # Get and update conversation cost
            conv_updated = get_conversation(conv_id, owner_id=user["id"])
            new_total_cost, new_total_tokens = calculate_new_cost(usage, cost, conv_updated)
            update_conversation_cost(conv_id, new_total_cost, new_total_tokens, owner_id=user["id"])
            session_cost = get_conversation_cost({"total_cost": new_total_cost, "total_tokens": new_total_tokens})
            
            # Build assistant message with assets
            assistant_msg = {
                "id": str(uuid4()),
                "role": "assistant",
                "content": assistant_text,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "assets": saved_assets,
            }
            
            # Append to conversation
            try:
                append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
            except KeyError:
                logger.warning(f"Failed to append assistant message to conversation {conv_id}")
            
            # Increment usage
            try:
                increment_user_usage(user["id"], delta=1)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")
            
            return UnifiedGenerateResponse(
                mode=actual_mode,
                conversation_id=conv_id,
                message=assistant_msg,
                text_response=assistant_text,
                assets=saved_assets,
                detected_mode=detected_mode,
                usage=usage,
                cost=cost,
                session_cost=session_cost
            )
        
        elif actual_mode == GenerationMode.VIDEO:
            logger.info(f"Routing to VIDEO generation - video_mode: {req.video_mode}")
            
            # Validate video mode requirements
            if req.video_mode == VideoMode.TEXT_TO_VIDEO and not prompt:
                raise HTTPException(status_code=400, detail="Prompt is required for text-to-video mode")
            
            if req.video_mode == VideoMode.FRAMES_TO_VIDEO and not req.start_frame:
                raise HTTPException(status_code=400, detail="Start frame is required for frames-to-video mode")
            
            if req.video_mode == VideoMode.REFERENCES_TO_VIDEO:
                if not req.reference_images and not req.style_image:
                    raise HTTPException(status_code=400, detail="At least one reference or style image required for references-to-video mode")
            
            if req.video_mode == VideoMode.EXTEND_VIDEO:
                if not req.input_video:
                    raise HTTPException(status_code=400, detail="Input video is required for extend-video mode")
            
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
            result = generate_video(
                prompt=prompt,
                model=req.model.value if req.model else "veo-3.1-fast-generate-preview",
                aspect_ratio=req.aspect_ratio.value if req.aspect_ratio else None,
                resolution=req.resolution.value if req.resolution else "720p",
                mode=req.video_mode.value if req.video_mode else VideoMode.TEXT_TO_VIDEO.value,
                owner_id=user["id"],
                start_frame=start_frame_dict,
                end_frame=end_frame_dict,
                is_looping=req.is_looping or False,
                reference_images=reference_images_list,
                style_image=style_image_dict,
                input_video=input_video_dict,
                input_images=input_images,
                avatar_id=req.avatar_id
            )
            
            message = result.content
            video_url = result.video_url
            video_uri = result.video_uri
            usage_metadata_raw = result.usage_metadata
            
            # Video uses fixed cost instead of token-based
            usage = None  # Video doesn't return token usage
            cost = calculate_video_cost()
            
            # Get and update conversation cost (no usage metadata for video)
            conv_updated = get_conversation(conv_id, owner_id=user["id"])
            new_total_cost, new_total_tokens = calculate_new_cost(usage, cost, conv_updated)
            update_conversation_cost(conv_id, new_total_cost, new_total_tokens, owner_id=user["id"])
            session_cost = get_conversation_cost({"total_cost": new_total_cost, "total_tokens": new_total_tokens})
            
            # Save video asset metadata
            from assets.services import add_asset_metadata
            video_asset_id = str(uuid4())
            add_asset_metadata(video_asset_id, "video", video_url, prompt, owner_id=user["id"])
            
            video_asset = {
                "id": video_asset_id,
                "type": "video",
                "url": video_url,
                "uri": video_uri,
                "prompt": prompt
            }
            
            # Build assistant message
            assistant_msg = {
                "id": str(uuid4()),
                "role": "assistant",
                "content": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "assets": [video_asset],
            }
            
            # Append to conversation
            try:
                append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
            except KeyError:
                logger.warning(f"Failed to append assistant message to conversation {conv_id}")
            
            # Increment usage
            try:
                increment_user_usage(user["id"], delta=1)
            except HTTPException:
                raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")
            
            return UnifiedGenerateResponse(
                mode=actual_mode,
                conversation_id=conv_id,
                message=assistant_msg,
                text_response=message,
                video_url=video_url,
                video_uri=video_uri,
                assets=[video_asset],
                detected_mode=detected_mode,
                usage=usage,
                cost=cost,
                session_cost=session_cost
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported mode: {actual_mode}")
    
    except HTTPException:
        raise
    except ValueError as e:
        # Validation errors (400 Bad Request)
        logger.warning(f"Validation error for user {user['id']}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Runtime errors (500 Internal Server Error or 503 Service Unavailable)
        error_msg = str(e)
        logger.error(f"Runtime error for user {user['id']}: {error_msg}")
        # Check if it's a service availability issue
        if "rate limit" in error_msg.lower() or "quota" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(status_code=503, detail=error_msg)
        else:
            raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        logger.error(f"Generation failed for user {user['id']}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

