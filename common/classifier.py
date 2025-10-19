"""Auto mode classifier for determining generation intent."""
from typing import List, Dict, Any, Optional

from config import Config
from utils.logger import get_logger
from common.models import GenerationMode

logger = get_logger("classifier")

# Gemini client
try:
    from google import genai
    from google.genai import types
except Exception:
    genai = None
    types = None


def build_classifier_prompt(prompt: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Build a classifier prompt with conversation history (using placeholders for assets).
    
    Args:
        prompt: Current user prompt
        conversation_history: Previous messages from conversation
    
    Returns:
        Formatted classifier prompt string
    """
    classifier_base = """You are a mode classifier. Analyze the user's request and conversation history to determine their intent.

Respond with ONLY ONE WORD from these options:
- TEXT: For conversational questions, explanations, analysis, discussions, or any text-based interaction
- IMAGE: For requests to generate, create, or show static visual content (photos, pictures, illustrations, etc.)
- VIDEO: For requests to generate, create, or show animated/motion content (videos, animations, moving sequences, etc.)

Consider:
- If they ask to "generate", "create", "make", "show me" with visual keywords → IMAGE or VIDEO
- If they ask questions, want explanations, discussions → TEXT
- "video", "animation", "motion", "moving" keywords → VIDEO
- "image", "picture", "photo", "draw", "paint" keywords → IMAGE
- If unclear or just chatting → TEXT

"""
    
    # Add conversation history with placeholders
    if conversation_history and len(conversation_history) > 0:
        classifier_base += "\nConversation history:\n"
        for msg in conversation_history[-5:]:  # Last 5 messages for context
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            assets = msg.get("assets", [])
            
            # Add asset placeholders
            if assets:
                asset_markers = []
                for asset in assets:
                    asset_type = asset.get("type", "asset")
                    if asset_type == "image":
                        asset_markers.append("[IMAGE]")
                    elif asset_type == "video":
                        asset_markers.append("[VIDEO]")
                    else:
                        asset_markers.append("[ASSET]")
                content = " ".join(asset_markers) + "\n" + content if content else " ".join(asset_markers)
            
            classifier_base += f"{role}: {content}\n"
        classifier_base += "\n"
    
    classifier_base += f"Current user request: {prompt}\n\nYour classification (TEXT, IMAGE, or VIDEO):"
    
    return classifier_base


def classify_generation_mode(
    prompt: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None
) -> GenerationMode:
    """
    Classify user intent to determine generation mode.
    
    Args:
        prompt: Current user prompt
        conversation_history: Previous messages from conversation (optional)
    
    Returns:
        GenerationMode (TEXT, IMAGE, or VIDEO)
    """
    if genai is None or types is None:
        logger.warning("genai not available, defaulting to TEXT mode")
        return GenerationMode.TEXT
    
    try:
        try:
            api_key = Config.get_gemini_api_key()
            client = genai.Client(api_key=api_key)
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini client for classification: {e}, defaulting to TEXT mode")
            return GenerationMode.TEXT
        
        model = Config.GEMINI_MODEL
        
        # Build classifier prompt
        try:
            classifier_prompt = build_classifier_prompt(prompt, conversation_history)
        except Exception as e:
            logger.warning(f"Failed to build classifier prompt: {e}, defaulting to TEXT mode")
            return GenerationMode.TEXT
        
        logger.info("Classifying generation mode with Gemini...")
        logger.debug(f"Classifier prompt: {classifier_prompt[:200]}...")
        
        try:
            # Use simple generation (not streaming) for quick classification
            contents = [types.Content(role="user", parts=[types.Part.from_text(text=classifier_prompt)])]
            
            config = types.GenerateContentConfig(
                response_modalities=["TEXT"],
                temperature=0.1,  # Low temperature for more deterministic classification
            )
            
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
        except Exception as e:
            logger.warning(f"Gemini API error during classification: {e}, defaulting to TEXT mode")
            return GenerationMode.TEXT
        
        # Extract classification
        try:
            if response and response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    text_response = ""
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            text_response += part.text
                    
                    # Parse response
                    classification = text_response.strip().upper()
                    logger.info(f"Gemini classification response: {classification}")
                    
                    # Map to GenerationMode
                    if "IMAGE" in classification:
                        logger.info("Classified as IMAGE mode")
                        return GenerationMode.IMAGE
                    elif "VIDEO" in classification:
                        logger.info("Classified as VIDEO mode")
                        return GenerationMode.VIDEO
                    else:
                        # Default to TEXT for unclear responses
                        logger.info("Classified as TEXT mode (default)")
                        return GenerationMode.TEXT
        except Exception as e:
            logger.warning(f"Failed to parse classification response: {e}")
        
        logger.warning("No valid classification response, defaulting to TEXT mode")
        return GenerationMode.TEXT
        
    except Exception as e:
        logger.error(f"Unexpected classification error: {e}, defaulting to TEXT mode")
        return GenerationMode.TEXT

