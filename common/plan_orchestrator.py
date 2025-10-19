"""Plan orchestration service for executing video generation plans."""
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

from common.models import (
    VideoGenerationPlan,
    SceneDefinition,
    SceneResult,
    VideoMode,
    CostInfo,
    ImageInput
)
from image.services import call_gemini_generate_stream_and_save
from videos.services import generate_video
from common.cost_service import calculate_video_cost, calculate_cost_from_usage, extract_usage_from_gemini_response
from utils.logger import get_logger

logger = get_logger("plan_orchestrator")


def generate_images_for_scene(
    scene: SceneDefinition,
    owner_id: Optional[str] = None,
    avatar_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Pre-generate reference images for a scene.
    
    Args:
        scene: SceneDefinition with image_prompts
        owner_id: User ID for asset ownership
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        List of generated image assets with metadata
    
    Raises:
        RuntimeError: If image generation fails
    """
    if not scene.pre_generate_images or not scene.image_prompts:
        return []
    
    logger.info(f"Pre-generating {len(scene.image_prompts)} images for scene '{scene.id}'")
    
    generated_images = []
    
    for i, img_prompt in enumerate(scene.image_prompts):
        try:
            logger.info(f"Generating image {i+1}/{len(scene.image_prompts)}: {img_prompt[:50]}...")
            
            # Call image generation service
            result = call_gemini_generate_stream_and_save(
                prompt=img_prompt,
                owner_id=owner_id,
                conversation_history=None,
                input_images=None,
                avatar_id=avatar_id
            )
            
            if result.assets and len(result.assets) > 0:
                generated_images.extend(result.assets)
                logger.info(f"Generated {len(result.assets)} images for prompt {i+1}")
            else:
                logger.warning(f"No images generated for prompt {i+1}")
            
        except Exception as e:
            logger.error(f"Failed to generate image {i+1} for scene '{scene.id}': {e}")
            # Continue with other images even if one fails
    
    logger.info(f"Pre-generated {len(generated_images)} total images for scene '{scene.id}'")
    return generated_images


def execute_single_scene(
    scene: SceneDefinition,
    owner_id: Optional[str],
    previous_video_uri: Optional[str] = None,
    pre_generated_images: Optional[List[Dict[str, Any]]] = None,
    default_aspect_ratio: str = "16:9",
    default_resolution: str = "720p",
    default_model: str = "veo-3.1-fast-generate-preview",
    avatar_id: Optional[str] = None
) -> SceneResult:
    """
    Execute a single scene's video generation.
    
    Args:
        scene: SceneDefinition to execute
        owner_id: User ID for asset ownership
        previous_video_uri: Video URI from dependency (for extend_video mode)
        pre_generated_images: Pre-generated reference images
        default_aspect_ratio: Default aspect ratio if not specified in scene
        default_resolution: Default resolution if not specified in scene
        default_model: Default model if not specified in scene
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        SceneResult with generation outcome
    """
    start_time = time.time()
    scene_id = scene.id
    
    logger.info(f"Executing scene '{scene_id}' with mode '{scene.mode.value}'")
    
    try:
        # Determine video generation parameters
        aspect_ratio = scene.aspect_ratio.value if scene.aspect_ratio else default_aspect_ratio
        resolution = scene.resolution.value if scene.resolution else default_resolution
        model = scene.model.value if scene.model else default_model
        
        # Build video generation parameters based on mode
        video_params = {
            "prompt": scene.prompt,
            "model": model,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "mode": scene.mode.value,
            "owner_id": owner_id,
            "avatar_id": avatar_id
        }
        
        # Handle different video modes
        if scene.mode == VideoMode.EXTEND_VIDEO:
            if not previous_video_uri:
                raise ValueError(f"Scene '{scene_id}' requires extend_video but no previous video URI provided")
            video_params["input_video"] = {"uri": previous_video_uri}
            logger.info(f"Extending video from URI: {previous_video_uri[:50]}...")
        
        elif scene.mode == VideoMode.FRAMES_TO_VIDEO:
            # Use pre-generated images as frames if available
            if pre_generated_images and len(pre_generated_images) > 0:
                # Use first image as start frame
                first_img = pre_generated_images[0]
                # TODO: Load image from URL and convert to base64
                logger.info(f"Using pre-generated image as start frame: {first_img.get('url')}")
                # For now, we'll skip frame setting and use text_to_video
                # Full implementation would require loading the image file
        
        elif scene.mode == VideoMode.REFERENCES_TO_VIDEO:
            # Use pre-generated images as references
            if pre_generated_images and len(pre_generated_images) > 0:
                # TODO: Load images from URLs and convert to base64
                logger.info(f"Using {len(pre_generated_images)} pre-generated images as references")
                # For now, we'll skip reference setting
                # Full implementation would require loading the image files
        
        # Call video generation service
        logger.info(f"Calling video generation for scene '{scene_id}'...")
        result = generate_video(**video_params)
        
        duration = time.time() - start_time
        
        # Calculate cost
        cost = None
        if result.usage_metadata:
            # For modes with token usage
            usage = extract_usage_from_gemini_response(result.usage_metadata)
            cost = calculate_cost_from_usage(usage, model)
        else:
            # Fixed video cost
            cost = calculate_video_cost()
        
        logger.info(f"Scene '{scene_id}' completed in {duration:.1f}s")
        
        return SceneResult(
            scene_id=scene_id,
            success=True,
            video_url=result.video_url,
            video_uri=result.video_uri,
            generated_images=pre_generated_images,
            error=None,
            duration_seconds=duration,
            cost=cost
        )
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        logger.error(f"Scene '{scene_id}' failed after {duration:.1f}s: {error_msg}")
        
        return SceneResult(
            scene_id=scene_id,
            success=False,
            video_url=None,
            video_uri=None,
            generated_images=pre_generated_images,
            error=error_msg,
            duration_seconds=duration,
            cost=None
        )


def execute_parallel_scenes(
    scenes: List[SceneDefinition],
    owner_id: Optional[str],
    scene_images: Dict[str, List[Dict[str, Any]]],
    default_aspect_ratio: str,
    default_resolution: str,
    default_model: str,
    max_workers: int = 3,
    avatar_id: Optional[str] = None
) -> List[SceneResult]:
    """
    Execute multiple independent scenes in parallel.
    
    Args:
        scenes: List of SceneDefinitions to execute
        owner_id: User ID
        scene_images: Dict mapping scene_id to pre-generated images
        default_aspect_ratio: Default aspect ratio
        default_resolution: Default resolution
        default_model: Default model
        max_workers: Maximum parallel workers
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        List of SceneResults
    """
    logger.info(f"Executing {len(scenes)} scenes in parallel (max_workers={max_workers})")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all scene executions
        future_to_scene = {
            executor.submit(
                execute_single_scene,
                scene,
                owner_id,
                None,  # No previous video for parallel scenes
                scene_images.get(scene.id, []),
                default_aspect_ratio,
                default_resolution,
                default_model,
                avatar_id
            ): scene
            for scene in scenes
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_scene):
            scene = future_to_scene[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Scene '{scene.id}' parallel execution: {'SUCCESS' if result.success else 'FAILED'}")
            except Exception as e:
                logger.error(f"Scene '{scene.id}' parallel execution raised exception: {e}")
                results.append(SceneResult(
                    scene_id=scene.id,
                    success=False,
                    video_url=None,
                    video_uri=None,
                    generated_images=None,
                    error=str(e),
                    duration_seconds=0.0,
                    cost=None
                ))
    
    return results


def execute_sequential_scenes(
    scenes: List[SceneDefinition],
    owner_id: Optional[str],
    scene_images: Dict[str, List[Dict[str, Any]]],
    default_aspect_ratio: str,
    default_resolution: str,
    default_model: str,
    avatar_id: Optional[str] = None
) -> List[SceneResult]:
    """
    Execute scenes sequentially, passing video URIs for extend_video mode.
    
    Args:
        scenes: List of SceneDefinitions in execution order
        owner_id: User ID
        scene_images: Dict mapping scene_id to pre-generated images
        default_aspect_ratio: Default aspect ratio
        default_resolution: Default resolution
        default_model: Default model
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        List of SceneResults
    """
    logger.info(f"Executing {len(scenes)} scenes sequentially")
    
    results = []
    previous_video_uri = None
    
    for scene in scenes:
        result = execute_single_scene(
            scene,
            owner_id,
            previous_video_uri,
            scene_images.get(scene.id, []),
            default_aspect_ratio,
            default_resolution,
            default_model,
            avatar_id
        )
        
        results.append(result)
        
        if result.success:
            # Update previous_video_uri for next scene
            if result.video_uri:
                previous_video_uri = result.video_uri
                logger.info(f"Scene '{scene.id}' completed, video URI available for next scene")
        else:
            logger.warning(f"Scene '{scene.id}' failed, sequential chain may be broken")
            # Continue with remaining scenes even if one fails
    
    return results


def execute_plan(
    plan: VideoGenerationPlan,
    owner_id: Optional[str] = None,
    default_aspect_ratio: str = "16:9",
    default_resolution: str = "720p",
    default_model: str = "veo-3.1-fast-generate-preview",
    max_parallel_workers: int = 3,
    avatar_id: Optional[str] = None
) -> List[SceneResult]:
    """
    Execute a complete video generation plan with intelligent orchestration.
    
    This function handles:
    - Pre-generating reference images for scenes that need them
    - Executing independent scenes in parallel
    - Executing dependent scenes sequentially
    - Managing video URIs for extend_video mode
    
    Args:
        plan: VideoGenerationPlan to execute
        owner_id: User ID for asset ownership
        default_aspect_ratio: Default aspect ratio for scenes
        default_resolution: Default resolution for scenes
        default_model: Default model for scenes
        max_parallel_workers: Maximum number of parallel video generations
        avatar_id: Optional avatar ID for character consistency across scenes
    
    Returns:
        List of SceneResults for all scenes
    
    Raises:
        ValueError: If plan is invalid
    """
    logger.info(f"Starting plan execution: {len(plan.scenes)} scenes")
    logger.info(f"Overall strategy: {plan.overall_strategy}")
    
    start_time = time.time()
    
    # Step 1: Pre-generate images for all scenes that need them
    logger.info("Step 1: Pre-generating reference images...")
    scene_images: Dict[str, List[Dict[str, Any]]] = {}
    
    for scene in plan.scenes:
        if scene.pre_generate_images:
            try:
                images = generate_images_for_scene(scene, owner_id, avatar_id)
                scene_images[scene.id] = images
            except Exception as e:
                logger.error(f"Failed to pre-generate images for scene '{scene.id}': {e}")
                scene_images[scene.id] = []
    
    logger.info(f"Pre-generated images for {len(scene_images)} scenes")
    
    # Step 2: Build scene lookup and execution order
    scene_lookup = {scene.id: scene for scene in plan.scenes}
    all_results: List[SceneResult] = []
    
    # Step 3: Execute parallel groups
    if plan.orchestration.parallel_groups:
        logger.info(f"Step 2: Executing {len(plan.orchestration.parallel_groups)} parallel groups...")
        
        for group_idx, group in enumerate(plan.orchestration.parallel_groups):
            logger.info(f"Executing parallel group {group_idx + 1}/{len(plan.orchestration.parallel_groups)}: {group}")
            
            group_scenes = [scene_lookup[scene_id] for scene_id in group if scene_id in scene_lookup]
            
            if not group_scenes:
                logger.warning(f"Parallel group {group_idx + 1} contains no valid scenes")
                continue
            
            group_results = execute_parallel_scenes(
                group_scenes,
                owner_id,
                scene_images,
                default_aspect_ratio,
                default_resolution,
                default_model,
                max_parallel_workers,
                avatar_id
            )
            
            all_results.extend(group_results)
    
    # Step 4: Execute sequential chains
    if plan.orchestration.sequential_chains:
        logger.info(f"Step 3: Executing {len(plan.orchestration.sequential_chains)} sequential chains...")
        
        for chain_idx, chain in enumerate(plan.orchestration.sequential_chains):
            logger.info(f"Executing sequential chain {chain_idx + 1}/{len(plan.orchestration.sequential_chains)}: {chain}")
            
            chain_scenes = [scene_lookup[scene_id] for scene_id in chain if scene_id in scene_lookup]
            
            if not chain_scenes:
                logger.warning(f"Sequential chain {chain_idx + 1} contains no valid scenes")
                continue
            
            chain_results = execute_sequential_scenes(
                chain_scenes,
                owner_id,
                scene_images,
                default_aspect_ratio,
                default_resolution,
                default_model,
                avatar_id
            )
            
            all_results.extend(chain_results)
    
    # Step 5: Handle any scenes not in orchestration (fallback to sequential)
    orchestrated_scene_ids = set()
    for group in plan.orchestration.parallel_groups:
        orchestrated_scene_ids.update(group)
    for chain in plan.orchestration.sequential_chains:
        orchestrated_scene_ids.update(chain)
    
    unorchestrated_scenes = [
        scene for scene in plan.scenes
        if scene.id not in orchestrated_scene_ids
    ]
    
    if unorchestrated_scenes:
        logger.warning(f"Found {len(unorchestrated_scenes)} unorchestrated scenes, executing sequentially")
        fallback_results = execute_sequential_scenes(
            unorchestrated_scenes,
            owner_id,
            scene_images,
            default_aspect_ratio,
            default_resolution,
            default_model,
            avatar_id
        )
        all_results.extend(fallback_results)
    
    # Summary
    total_time = time.time() - start_time
    success_count = sum(1 for r in all_results if r.success)
    failure_count = len(all_results) - success_count
    
    logger.info(f"Plan execution completed in {total_time:.1f}s")
    logger.info(f"Results: {success_count} succeeded, {failure_count} failed")
    
    # Sort results by scene order in plan
    scene_order = {scene.id: idx for idx, scene in enumerate(plan.scenes)}
    all_results.sort(key=lambda r: scene_order.get(r.scene_id, 999))
    
    return all_results

