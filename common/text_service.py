"""Text generation service using Gemini."""
import base64
from typing import Optional, List, Dict, Any

from config import Config
from common.personas import get_active_persona
from common.models import GenerationServiceResponse
from utils.logger import get_logger
from common.error_messages import ErrorCode

logger = get_logger("text_service")

# Gemini client
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


def build_gemini_contents_with_images(
    messages: List[Dict[str, Any]], 
    current_prompt: str,
    input_images: Optional[List[Dict[str, str]]] = None
) -> List:
    """
    Convert conversation messages and current prompt to Gemini Content format.
    
    Args:
        messages: List of conversation messages with structure:
                  {role: 'user'|'assistant', content: str, assets?: [{url, ...}], ...}
        current_prompt: Current user prompt
        input_images: Optional list of images to include with current prompt
                      Format: [{"mime_type": "...", "data": "base64..."}]
    
    Returns:
        List of types.Content objects suitable for Gemini API
    """
    if not types:
        raise RuntimeError("genai types not available")
    
    contents = []
    
    # Add conversation history with placeholders for assets
    for msg in messages:
        role = msg.get("role")
        if not role:
            continue
        
        # Map 'assistant' to 'model' for Gemini API
        gemini_role = "model" if role == "assistant" else "user"
        
        parts = []
        
        # Add text content
        content_text = msg.get("content", "").strip()
        
        # Check if message has assets and add placeholders
        assets = msg.get("assets", [])
        if assets:
            asset_placeholders = []
            for asset in assets:
                asset_type = asset.get("type", "asset")
                if asset_type == "image":
                    asset_placeholders.append("[IMAGE]")
                elif asset_type == "video":
                    asset_placeholders.append("[VIDEO]")
                else:
                    asset_placeholders.append("[ASSET]")
            
            if asset_placeholders:
                placeholder_text = " ".join(asset_placeholders)
                if content_text:
                    content_text = f"{placeholder_text}\n{content_text}"
                else:
                    content_text = placeholder_text
        
        if content_text:
            parts.append(types.Part.from_text(text=content_text))
        
        # Only add content if we have parts
        if parts:
            contents.append(types.Content(role=gemini_role, parts=parts))
    
    # Add current user prompt with optional images
    current_parts = []
    
    # Add images first if provided
    if input_images:
        for img in input_images:
            try:
                try:
                    image_bytes = base64.b64decode(img["data"])
                except Exception as e:
                    logger.warning(f"Failed to decode base64 image data: {e}")
                    continue
                
                current_parts.append(types.Part(
                    inline_data=types.Blob(
                        mime_type=img.get("mime_type", "image/png"),
                        data=image_bytes
                    )
                ))
                logger.debug(f"Added input image: {img.get('mime_type', 'image/png')}")
            except Exception as e:
                logger.warning(f"Failed to process input image: {e}")
                # Continue with other images
    
    # Add text prompt
    if current_prompt:
        current_parts.append(types.Part.from_text(text=current_prompt))
    
    if current_parts:
        contents.append(types.Content(role="user", parts=current_parts))
    
    return contents


def generate_text(
    prompt: str,
    owner_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    input_images: Optional[List[Dict[str, str]]] = None,
    avatar_id: Optional[str] = None
) -> GenerationServiceResponse:
    """
    Generate text response using Gemini with conversation context.
    
    Args:
        prompt: Current user prompt
        owner_id: User ID for persona integration
        conversation_history: Previous messages from conversation (optional)
        input_images: Optional images to include with prompt
                      Format: [{"mime_type": "...", "data": "base64..."}]
        avatar_id: Optional avatar ID for character consistency (rarely used for text)
    
    Returns:
        GenerationServiceResponse with content and usage_metadata
    """
    try:
        if genai is None or types is None:
            logger.error("Gemini client not available")
            raise RuntimeError("AI service is not configured properly")
        
        try:
            api_key = Config.get_gemini_api_key()
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise RuntimeError("Failed to connect to AI service")
        
        model = Config.GEMINI_MODEL
        
        # Get active persona for system instruction
        system_instruction_text = "You are a helpful AI assistant."
        if owner_id:
            try:
                active_persona = get_active_persona(owner_id)
                if active_persona and active_persona.get("description"):
                    system_instruction_text = active_persona["description"]
                    logger.info(f"Using persona '{active_persona.get('name')}' for user {owner_id}")
                else:
                    logger.warning(f"No active persona found for user {owner_id}, using default system instruction")
            except Exception as e:
                logger.warning(f"Failed to get active persona: {e}, using default")
        
        # Load and prepend avatar if provided
        avatar_instruction_added = False
        if avatar_id and owner_id:
            try:
                from avatars.services import load_avatar_as_base64
                avatar_image = load_avatar_as_base64(avatar_id, owner_id)
                # Prepend avatar to input_images
                if input_images:
                    input_images = [avatar_image] + input_images
                else:
                    input_images = [avatar_image]
                # Prepend instruction to use avatar consistently
                prompt = f"Use this avatar consistently in your generations. {prompt}"
                avatar_instruction_added = True
                logger.info(f"Using avatar {avatar_id} for text generation with consistency instruction")
            except Exception as e:
                logger.warning(f"Failed to load avatar {avatar_id}: {e}")
                # Continue without avatar (optional parameter)
        
        # Build contents from conversation history
        history_to_use = []
        if conversation_history:
            try:
                # Limit to last N messages based on config
                history_depth = Config.CONVERSATION_HISTORY_DEPTH
                history_to_use = conversation_history[-history_depth:] if len(conversation_history) > history_depth else conversation_history
                logger.info(f"Building request with {len(history_to_use)} historical messages")
            except Exception as e:
                logger.warning(f"Failed to process conversation history: {e}")
                history_to_use = []
        
        try:
            contents = build_gemini_contents_with_images(history_to_use, prompt, input_images)
        except Exception as e:
            logger.error(f"Failed to build contents: {e}")
            raise RuntimeError("Failed to prepare AI request")
        
        logger.info(f"Total contents in request: {len(contents)}")
        
        try:
            generate_content_config = types.GenerateContentConfig(
                response_modalities=["TEXT"],
                system_instruction=[types.Part.from_text(text=system_instruction_text)],
            )
        except Exception as e:
            logger.error(f"Failed to create generation config: {e}")
            raise RuntimeError("Failed to configure AI request")
        
        assembled_text_parts = []
        chunk_count = 0
        last_chunk = None
        
        logger.info(f"Streaming text response from Gemini model: {model}")
        
        try:
            for chunk in client.models.generate_content_stream(
                model=model, contents=contents, config=generate_content_config
            ):
                chunk_count += 1
                last_chunk = chunk  # Keep track of last chunk for usage_metadata
                
                if not (chunk and chunk.candidates and chunk.candidates[0].content):
                    logger.debug(f"Chunk {chunk_count}: empty or no content")
                    continue
                
                candidate = chunk.candidates[0]
                content = candidate.content
                
                if getattr(content, "parts", None):
                    for part in content.parts:
                        text = getattr(part, "text", None)
                        if text:
                            assembled_text_parts.append(text)
                            logger.debug(f"Chunk {chunk_count}: text part ({len(text)} chars)")
        except Exception as e:
            logger.error(f"Error during text generation streaming: {e}")
            error_msg = str(e).lower()
            if "rate" in error_msg or "quota" in error_msg:
                raise RuntimeError("AI service rate limit exceeded. Please try again in a few minutes.")
            elif "timeout" in error_msg:
                raise RuntimeError("AI service timeout. Please try again with a simpler request.")
            else:
                raise RuntimeError(f"AI service error: {str(e)}")
        
        assembled_text = "".join(assembled_text_parts)
        
        if not assembled_text.strip():
            logger.warning("No content generated from Gemini")
            raise RuntimeError("No content was generated. Please try rephrasing your request.")
        
        # Extract usage metadata from last chunk
        usage_metadata = None
        try:
            if last_chunk and hasattr(last_chunk, 'usage_metadata'):
                usage_metadata = last_chunk.usage_metadata
                if usage_metadata:
                    prompt_tokens = getattr(usage_metadata, 'prompt_token_count', 0) or 0
                    completion_tokens = getattr(usage_metadata, 'candidates_token_count', 0) or 0
                    total_tokens = getattr(usage_metadata, 'total_token_count', 0) or 0
                    logger.info(f"Usage: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total tokens")
        except Exception as e:
            logger.warning(f"Failed to extract usage metadata: {e}")
            # Continue without usage metadata
        
        logger.info(f"Text generation complete: {chunk_count} chunks, {len(assembled_text)} chars")
        
        return GenerationServiceResponse(
            content=assembled_text.strip(),
            usage_metadata=usage_metadata
        )
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in text generation: {e}")
        raise RuntimeError(f"Text generation failed: {str(e)}")

