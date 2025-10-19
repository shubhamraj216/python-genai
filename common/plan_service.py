"""Script planning service for intelligent video generation orchestration."""
import json
import hashlib
from datetime import datetime, timezone
from typing import Optional

from config import Config
from common.models import (
    VideoGenerationPlan,
    SceneDefinition,
    OrchestrationStrategy,
    VideoMode,
    AspectRatio,
    Resolution,
    VeoModel,
    CostInfo
)
from utils.logger import get_logger

logger = get_logger("plan_service")

# Gemini client
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


def build_planning_prompt(script: str) -> str:
    """
    Build a comprehensive planning prompt for the AI to analyze and create execution plan.
    
    Args:
        script: User's narrative script
    
    Returns:
        Formatted planning prompt
    """
    prompt = f"""You are an expert video production planner specializing in breaking down narrative scripts into optimal video generation plans.

SCRIPT:
{script}

TASK:
Analyze this script and create a detailed execution plan for generating videos. Break the script into logical scenes/shots suitable for AI video generation (typically 2–10 seconds each). Treat any camera angle change, cut, or shot change as a NEW scene.

For EACH scene, decide:

1. **Video Generation Mode** — choose exactly one:
   - **text_to_video**: For simple, standalone shots with no visual continuity requirements. Good for isolated beats where all visuals can be inferred from text.
   
   - **frames_to_video**: When you need precise control over start/end states or pose/action continuity within a new shot. Use for:
     * Specific transitions (door opening mid-action, object transforming)
     * Looping animations (set is_looping: true)
     * Shots requiring exact first/last frames or pose-matching to prior shots
   
   - **references_to_video**: When cross-shot consistency is critical. Use for:
     * Maintaining consistent character appearance/outfits across shots
     * Matching specific props/vehicles/environments across shots
     * Preserving a defined style/cinematography across different angles or locations
     * (For angle changes of the same moment, prefer references_to_video and describe what must match from the prior shot.)
   
   - **extend_video**: **ONLY** to continue the **same continuous shot** with no cut (same camera move, same framing continuing). Use for:
     * Continuous action without any cut
     * Camera movements that span beyond a single duration segment
     * Maintaining temporal/spatial continuity within the same uninterrupted take

2. **Image Pre-generation Strategy**:
   - Set `pre_generate_images: true` when references/consistency are needed across shots
   - Provide specific `image_prompts` for characters, outfits, key props, vehicles, environments, and style references
   - Prefer pre-generation when the same visual elements appear in multiple scenes or angles

3. **Dependencies**:
   - List scene IDs this scene depends on **only** when using `extend_video` (continuing the same uninterrupted take)
   - For angle/cut changes, **do not** use extend dependencies; instead rely on references_to_video or frames_to_video

4. **Scene-Specific Settings** (optional overrides):
   - aspect_ratio: "16:9" (landscape) or "9:16" (portrait)
   - resolution: "720p" or "1080p"
   - model: "veo-3.1-fast-generate-preview" (faster) or "veo-3.1-generate-preview" (higher quality)

5. **Orchestration Strategy**:
   - Group independent shots into `parallel_groups` for concurrent generation
   - Chain ONLY uninterrupted takes using `sequential_chains` with `extend_video`
   - Balance speed (parallel) vs. continuity (sequential)

IMPORTANT GUIDELINES:
- **Angle/Cut Rule**: Any camera angle change or editorial cut starts a NEW scene. Use **references_to_video** for cross-shot consistency; use **frames_to_video** when you must match specific starting/ending poses or states.
- **Extend Rule**: Use **extend_video ONLY** when the same shot continues without any cut. Keep camera position, focal length, staging, lighting, and props continuous.
- Each scene should be 2–10 seconds.
- Optimize prompts with explicit visual detail: camera angle, lens/FOV, blocking, lighting, props, environment, motion, and composition. For angle changes, explicitly state: “match character, outfit, props, environment from scene_X.”
- Pre-generate images for recurring elements (characters, props, vehicles, sets) across multiple shots or locations.
- For same character in different locations or angles: prefer **references_to_video** (with pre-generated images).
- For precise motion continuity within a new shot: prefer **frames_to_video** and specify the opening/closing frame states.
- Provide clear reasoning for each choice (why this mode, how consistency is enforced).

OUTPUT FORMAT (JSON only, no markdown):
{{
  "scenes": [
    {{
      "id": "scene_1",
      "description": "Brief description of what happens in this shot from the original script",
      "prompt": "Detailed, optimized prompt with visual details, lens, angle, lighting, blocking, props, and any 'match from scene_X' notes.",
      "mode": "text_to_video",
      "duration_hint": "5s",
      "pre_generate_images": false,
      "image_prompts": [],
      "dependencies": [],
      "reasoning": "Why this mode and strategy were chosen (e.g., angle change → references_to_video; uninterrupted take → extend_video; precise start/end → frames_to_video).",
      "aspect_ratio": "16:9",
      "resolution": "720p",
      "model": "veo-3.1-fast-generate-preview"
    }}
  ],
  "orchestration": {{
    "parallel_groups": [["scene_1", "scene_2"], ["scene_3"]],
    "sequential_chains": [["scene_4", "scene_5"]]
  }},
  "overall_strategy": "High-level explanation of the approach; note which shots are uninterrupted extends vs. angle/cut changes using references/frames."
}}

CRITICAL RULES:
1. Output ONLY valid JSON. No markdown code blocks, no explanations outside the JSON structure.
2. Keep plans under 10 scenes maximum.
3. For `extend_video` (same continuous shot):
   - Maintain identical camera/lens, blocking, props, and environmental details
   - Each prompt must logically continue the previous take
   - Keep visual style and lighting consistent
4. **Never use extend_video for angle/cut changes.** For angle/cut changes, use references_to_video (and frames_to_video if exact start/end states are needed).
5. Use `dependencies` ONLY to indicate continuation with `extend_video`.
6. Keep fewer than 6 scenes in the plan whenever possible.
7. In every prompt, specify camera angle/lens, subject placement, prop positions, and environment details; for cross-shot consistency, include “match from scene_X”.
"""

    return prompt


def create_plan_from_script(script: str) -> VideoGenerationPlan:
    """
    Create an intelligent execution plan from a narrative script using AI.
    
    Args:
        script: Narrative script text from user
    
    Returns:
        VideoGenerationPlan with scenes and orchestration strategy
    
    Raises:
        RuntimeError: If AI service is unavailable or planning fails
        ValueError: If script is invalid or AI returns malformed plan
    """
    if not script or not script.strip():
        raise ValueError("Script cannot be empty")
    
    if genai is None or types is None:
        raise RuntimeError("AI service not available (google-genai not installed)")
    
    try:
        api_key = Config.get_gemini_api_key()
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        raise RuntimeError("Failed to connect to AI service")
    
    model = Config.GEMINI_MODEL
    
    # Build planning prompt
    planning_prompt = build_planning_prompt(script)
    
    logger.info("Creating execution plan from script using AI...")
    logger.debug(f"Script length: {len(script)} characters")
    
    try:
        # Use Gemini to generate the plan
        contents = [types.Content(
            role="user",
            parts=[types.Part.from_text(text=planning_prompt)]
        )]
        
        config = types.GenerateContentConfig(
            response_modalities=["TEXT"],
            temperature=0.7,  # Balanced creativity and consistency
        )
        
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
        
    except Exception as e:
        logger.error(f"AI API error during planning: {e}")
        raise RuntimeError(f"Failed to generate plan: {str(e)}")
    
    # Extract plan from response
    try:
        if not (response and response.candidates and len(response.candidates) > 0):
            raise ValueError("No response from AI")
        
        candidate = response.candidates[0]
        if not (candidate.content and candidate.content.parts):
            raise ValueError("Empty response from AI")
        
        text_response = ""
        for part in candidate.content.parts:
            if hasattr(part, "text") and part.text:
                text_response += part.text
        
        logger.debug(f"AI planning response: {text_response[:500]}...")
        
        # Parse JSON response (handle potential markdown wrapping)
        text_response = text_response.strip()
        
        # Remove markdown code blocks if present
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        elif text_response.startswith("```"):
            text_response = text_response[3:]
        
        if text_response.endswith("```"):
            text_response = text_response[:-3]
        
        text_response = text_response.strip()
        
        # Parse JSON
        plan_dict = json.loads(text_response)
        
        logger.info(f"Parsed plan with {len(plan_dict.get('scenes', []))} scenes")
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Response was: {text_response[:1000]}")
        raise ValueError("AI returned invalid JSON plan")
    except Exception as e:
        logger.error(f"Failed to extract plan from response: {e}")
        raise ValueError(f"Failed to process AI response: {str(e)}")
    
    # Convert dict to Pydantic models
    try:
        scenes = []
        for scene_dict in plan_dict.get("scenes", []):
            # Convert mode string to VideoMode enum
            mode_str = scene_dict.get("mode", "text_to_video")
            try:
                mode = VideoMode(mode_str)
            except ValueError:
                logger.warning(f"Invalid mode '{mode_str}', defaulting to text_to_video")
                mode = VideoMode.TEXT_TO_VIDEO
            
            # Convert optional aspect_ratio
            aspect_ratio = None
            if "aspect_ratio" in scene_dict and scene_dict["aspect_ratio"]:
                try:
                    aspect_ratio = AspectRatio(scene_dict["aspect_ratio"])
                except ValueError:
                    pass
            
            # Convert optional resolution
            resolution = None
            if "resolution" in scene_dict and scene_dict["resolution"]:
                try:
                    resolution = Resolution(scene_dict["resolution"])
                except ValueError:
                    pass
            
            # Convert optional model
            model_enum = None
            if "model" in scene_dict and scene_dict["model"]:
                try:
                    model_enum = VeoModel(scene_dict["model"])
                except ValueError:
                    pass
            
            scene = SceneDefinition(
                id=scene_dict["id"],
                description=scene_dict.get("description", ""),
                prompt=scene_dict["prompt"],
                mode=mode,
                duration_hint=scene_dict.get("duration_hint", "5s"),
                pre_generate_images=scene_dict.get("pre_generate_images", False),
                image_prompts=scene_dict.get("image_prompts"),
                dependencies=scene_dict.get("dependencies", []),
                reasoning=scene_dict.get("reasoning", ""),
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                model=model_enum
            )
            scenes.append(scene)
        
        orchestration_dict = plan_dict.get("orchestration", {})
        orchestration = OrchestrationStrategy(
            parallel_groups=orchestration_dict.get("parallel_groups", []),
            sequential_chains=orchestration_dict.get("sequential_chains", [])
        )
        
        # Calculate estimated duration
        total_seconds = 0
        for scene in scenes:
            duration_str = scene.duration_hint
            # Parse duration (e.g., "5s" -> 5)
            try:
                seconds = int(duration_str.rstrip('s'))
                total_seconds += seconds
            except:
                total_seconds += 5  # default
        
        estimated_duration = f"{total_seconds}s"
        
        # Generate script hash for validation
        script_hash = hashlib.sha256(script.encode()).hexdigest()[:16]
        
        plan = VideoGenerationPlan(
            scenes=scenes,
            orchestration=orchestration,
            overall_strategy=plan_dict.get("overall_strategy", ""),
            estimated_duration=estimated_duration,
            created_at=datetime.now(timezone.utc).isoformat(),
            script_hash=script_hash
        )
        
        logger.info(f"Successfully created plan: {len(scenes)} scenes, estimated {estimated_duration} total")
        return plan
        
    except Exception as e:
        logger.error(f"Failed to convert plan dict to models: {e}")
        raise ValueError(f"Invalid plan structure: {str(e)}")


def validate_plan(plan: VideoGenerationPlan) -> bool:
    """
    Validate a plan for consistency and correctness.
    
    Args:
        plan: VideoGenerationPlan to validate
    
    Returns:
        True if valid
    
    Raises:
        ValueError: If plan is invalid with detailed error message
    """
    if not plan.scenes or len(plan.scenes) == 0:
        raise ValueError("Plan must contain at least one scene")
    
    # Check for duplicate scene IDs
    scene_ids = [scene.id for scene in plan.scenes]
    if len(scene_ids) != len(set(scene_ids)):
        raise ValueError("Plan contains duplicate scene IDs")
    
    # Validate dependencies reference existing scenes
    for scene in plan.scenes:
        for dep_id in scene.dependencies:
            if dep_id not in scene_ids:
                raise ValueError(f"Scene '{scene.id}' depends on non-existent scene '{dep_id}'")
    
    # Validate extend_video mode has dependencies
    for scene in plan.scenes:
        if scene.mode == VideoMode.EXTEND_VIDEO and not scene.dependencies:
            raise ValueError(f"Scene '{scene.id}' uses extend_video mode but has no dependencies")
    
    # Validate orchestration references existing scenes
    all_orchestration_scenes = set()
    for group in plan.orchestration.parallel_groups:
        for scene_id in group:
            if scene_id not in scene_ids:
                raise ValueError(f"Orchestration references non-existent scene '{scene_id}'")
            all_orchestration_scenes.add(scene_id)
    
    for chain in plan.orchestration.sequential_chains:
        for scene_id in chain:
            if scene_id not in scene_ids:
                raise ValueError(f"Orchestration references non-existent scene '{scene_id}'")
            all_orchestration_scenes.add(scene_id)
    
    logger.info(f"Plan validation successful: {len(plan.scenes)} scenes")
    return True


def estimate_plan_cost(plan: VideoGenerationPlan) -> CostInfo:
    """
    Estimate the cost of executing a plan.
    
    Args:
        plan: VideoGenerationPlan to estimate
    
    Returns:
        CostInfo with estimated costs
    
    Note:
        This is a rough estimate based on fixed per-video costs.
        Actual costs may vary based on generation time and model used.
    """
    # Video generation has fixed costs per video (no token-based pricing)
    # Rough estimates based on Gemini Veo pricing
    
    cost_per_video = 0.0
    image_cost_per_generation = 0.0
    
    # Estimate video costs
    for scene in plan.scenes:
        # Different models may have different costs
        if scene.model == VeoModel.VEO:
            cost_per_video += 0.10  # Higher quality, higher cost (estimate)
        else:
            cost_per_video += 0.05  # Fast model, lower cost (estimate)
    
    # Estimate image pre-generation costs
    for scene in plan.scenes:
        if scene.pre_generate_images and scene.image_prompts:
            # Rough estimate: ~$0.01 per image
            image_cost_per_generation += len(scene.image_prompts) * 0.01
    
    total_cost = cost_per_video + image_cost_per_generation
    
    logger.info(f"Estimated plan cost: ${total_cost:.2f} ({len(plan.scenes)} videos, {image_cost_per_generation/0.01 if image_cost_per_generation > 0 else 0:.0f} images)")
    
    return CostInfo(
        prompt_cost=0.0,
        completion_cost=total_cost,
        total_cost=total_cost,
        currency="USD"
    )

