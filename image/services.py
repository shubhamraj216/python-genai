"""Image generation services - Gemini integration."""
import os
import base64
import mimetypes
from uuid import uuid4
from typing import Optional, List, Dict, Any

from config import Config
from common.personas import get_active_persona
from common.models import GenerationServiceResponse
from utils.logger import get_logger

logger = get_logger("image.services")

# Gemini client (ensure google-genai installed and GEMINI_API_KEY env var set)
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


def save_binary_file_return_url(file_name: str, data: bytes) -> str:
    """Save binary file to assets directory and return URL."""
    try:
        path = os.path.join(Config.ASSETS_DIR, file_name)
        with open(path, "wb") as f:
            f.write(data)
        # Return relative URL path (served by static mount)
        return f"/assets/generated/{file_name}"
    except (IOError, OSError) as e:
        logger.error(f"Failed to save file {file_name}: {e}")
        raise RuntimeError(f"Failed to save generated image: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error saving file {file_name}: {e}")
        raise RuntimeError("Failed to save generated image")


def build_gemini_contents(messages: List[Dict[str, Any]]) -> List:
    """
    Convert conversation message history to Gemini Content format.
    
    Args:
        messages: List of conversation messages with structure:
                  {role: 'user'|'assistant', content: str, assets?: [{url, ...}], ...}
    
    Returns:
        List of types.Content objects suitable for Gemini API
    """
    if not types:
        raise RuntimeError("genai types not available")
    
    contents = []
    
    for msg in messages:
        role = msg.get("role")
        if not role:
            continue
        
        # Map 'assistant' to 'model' for Gemini API
        gemini_role = "model" if role == "assistant" else "user"
        
        parts = []
        
        # Add text content
        content_text = msg.get("content", "").strip()
        if content_text:
            parts.append(types.Part.from_text(text=content_text))
        
        # Add image assets (for assistant messages with generated images)
        assets = msg.get("assets", [])
        for asset in assets:
            asset_url = asset.get("url")
            if not asset_url:
                continue
            
            # Convert URL path to filesystem path
            # URL format: /assets/generated/{filename}
            if asset_url.startswith("/assets/generated/"):
                filename = asset_url.replace("/assets/generated/", "")
                file_path = os.path.join(Config.ASSETS_DIR, filename)
                
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            image_data = f.read()
                        
                        # Guess MIME type from file extension
                        mime_type, _ = mimetypes.guess_type(file_path)
                        if not mime_type:
                            mime_type = "image/png"  # default
                        
                        # Create inline data part
                        parts.append(types.Part(
                            inline_data=types.Blob(
                                mime_type=mime_type,
                                data=image_data
                            )
                        ))
                        logger.debug(f"Added image asset to history: {filename} ({mime_type})")
                    except Exception as e:
                        logger.warning(f"Failed to read asset file {file_path}: {e}")
                else:
                    logger.warning(f"Asset file not found: {file_path}")
        
        # Only add content if we have parts
        if parts:
            contents.append(types.Content(role=gemini_role, parts=parts))
    
    return contents


def call_gemini_generate_stream_and_save(
    prompt: str, 
    owner_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    input_images: Optional[List[Dict[str, str]]] = None,
    avatar_id: Optional[str] = None
) -> GenerationServiceResponse:
    """
    Call Gemini to generate images based on prompt with conversation context.
    Uses the active persona's description as system instruction.
    
    Args:
        prompt: Current user prompt
        owner_id: User ID for persona and asset ownership
        conversation_history: Previous messages from conversation (optional)
        input_images: Optional images to include with prompt
                      Format: [{"mime_type": "...", "data": "base64..."}]
        avatar_id: Optional avatar ID for character consistency
    
    Returns:
        GenerationServiceResponse with content, assets, and usage_metadata
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
        system_instruction_text = "You are an image-generation assistant."
        if owner_id:
            try:
                active_persona = get_active_persona(owner_id)
                if active_persona and active_persona.get("description"):
                    system_instruction_text = active_persona["description"]
                    logger.info(f"Using persona '{active_persona.get('name')}' (id: {active_persona.get('id')}) for user {owner_id}")
                    logger.debug(f"System instruction: {system_instruction_text[:100]}...")
                else:
                    logger.warning(f"No active persona found for user {owner_id}, using default system instruction")
            except Exception as e:
                logger.warning(f"Failed to get active persona: {e}, using default")
        else:
            logger.warning("No owner_id provided, using default system instruction")

        # Build contents from conversation history
        contents = []
        if conversation_history:
            # Limit to last N messages based on config
            history_depth = Config.CONVERSATION_HISTORY_DEPTH
            recent_messages = conversation_history[-history_depth:] if len(conversation_history) > history_depth else conversation_history
            
            logger.info(f"Building Gemini request with {len(recent_messages)} historical messages (depth limit: {history_depth})")
            
            contents = build_gemini_contents(recent_messages)
            
            # Log structure for debugging
            for idx, content in enumerate(contents):
                parts_info = []
                for part in content.parts:
                    if hasattr(part, 'text') and part.text:
                        parts_info.append(f"text({len(part.text)} chars)")
                    elif hasattr(part, 'inline_data') and part.inline_data:
                        parts_info.append(f"image({part.inline_data.mime_type})")
                logger.debug(f"Content[{idx}] role={content.role}, parts=[{', '.join(parts_info)}]")
        
        # Append current user prompt with optional avatar and input images
        current_parts = []
        
        # Load and prepend avatar if provided
        avatar_instruction_added = False
        if avatar_id and owner_id:
            try:
                from avatars.services import load_avatar_as_base64
                avatar_image = load_avatar_as_base64(avatar_id, owner_id)
                # Prepend avatar as first image
                if input_images:
                    input_images = [avatar_image] + input_images
                else:
                    input_images = [avatar_image]
                # Prepend instruction to use avatar consistently
                prompt = f"Use this avatar consistently in your generations. {prompt}"
                avatar_instruction_added = True
                logger.info(f"Using avatar {avatar_id} for image generation with consistency instruction")
            except Exception as e:
                logger.warning(f"Failed to load avatar {avatar_id}: {e}")
                # Continue without avatar (optional parameter)
        
        # Add input images first if provided
        if input_images:
            for img in input_images:
                try:
                    image_bytes = base64.b64decode(img["data"])
                    current_parts.append(types.Part(
                        inline_data=types.Blob(
                            mime_type=img["mime_type"],
                            data=image_bytes
                        )
                    ))
                    logger.info(f"Added input image: {img['mime_type']}")
                except Exception as e:
                    logger.warning(f"Failed to decode input image: {e}")
        
        # Add text prompt
        current_parts.append(types.Part.from_text(text=prompt))
        
        contents.append(types.Content(role="user", parts=current_parts))
        
        logger.info(f"Total contents in request: {len(contents)} (including current prompt with {len(input_images) if input_images else 0} images)")
        
        generate_content_config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            system_instruction=[types.Part.from_text(text=system_instruction_text)],
        )

        assembled_text_parts = []
        saved_assets = []
        chunk_count = 0
        last_chunk = None

        # Import here to avoid circular dependency
        from assets.services import add_asset_metadata

        logger.info(f"Streaming response from Gemini model: {model}")
        
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
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        file_extension = mimetypes.guess_extension(inline.mime_type) or ".bin"
                        aid = str(uuid4())
                        filename = f"{aid}{file_extension}"
                        url = save_binary_file_return_url(filename, inline.data)
                        # persist metadata immediately (with owner)
                        add_asset_metadata(aid, "image" if inline.mime_type.startswith("image/") else "file", url, prompt, owner_id)
                        saved_assets.append({"id": aid, "type": "image", "url": url, "prompt": prompt})
                        logger.info(f"Chunk {chunk_count}: saved image asset {filename} ({inline.mime_type}, {len(inline.data)} bytes)")
                    else:
                        # maybe text part
                        text = getattr(part, "text", None)
                        if text:
                            assembled_text_parts.append(text)
                            logger.debug(f"Chunk {chunk_count}: text part ({len(text)} chars)")

        assembled_text = "\n".join(p for p in assembled_text_parts if p)
        
        # Extract usage metadata from last chunk
        usage_metadata = None
        if last_chunk and hasattr(last_chunk, 'usage_metadata'):
            usage_metadata = last_chunk.usage_metadata
            if usage_metadata:
                prompt_tokens = getattr(usage_metadata, 'prompt_token_count', 0) or 0
                completion_tokens = getattr(usage_metadata, 'candidates_token_count', 0) or 0
                total_tokens = getattr(usage_metadata, 'total_token_count', 0) or 0
                logger.info(f"Usage: {prompt_tokens} prompt + {completion_tokens} completion = {total_tokens} total tokens")
        
        logger.info(f"Generation complete: {chunk_count} chunks, {len(saved_assets)} assets, {len(assembled_text)} chars text")
        
        return GenerationServiceResponse(
            content=assembled_text.strip(),
            assets=saved_assets,
            usage_metadata=usage_metadata
        )
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in image generation: {e}")
        raise RuntimeError(f"Image generation failed: {str(e)}")

