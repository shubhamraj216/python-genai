"""Cost calculation and tracking service."""
from typing import Optional, Dict, Any, Tuple
from config import Config
from common.models import UsageMetadata, CostInfo, SessionCostInfo
from utils.logger import get_logger

logger = get_logger("cost_service")


def extract_usage_from_gemini_response(response_chunk) -> Optional[UsageMetadata]:
    """
    Extract usage metadata from Gemini API response.
    
    Args:
        response_chunk: Gemini API response object
    
    Returns:
        UsageMetadata object or None if not available
    """
    try:
        if hasattr(response_chunk, 'usage_metadata') and response_chunk.usage_metadata:
            usage = response_chunk.usage_metadata
            prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
            completion_tokens = getattr(usage, 'candidates_token_count', 0) or 0
            total_tokens = getattr(usage, 'total_token_count', 0) or 0
            
            # If total not provided, calculate it
            if not total_tokens and (prompt_tokens or completion_tokens):
                total_tokens = prompt_tokens + completion_tokens
            
            return UsageMetadata(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
    except Exception as e:
        logger.warning(f"Failed to extract usage metadata: {e}")
    
    return None


def calculate_cost_from_usage(
    usage: UsageMetadata,
    input_price_per_million: Optional[float] = None,
    output_price_per_million: Optional[float] = None
) -> CostInfo:
    """
    Calculate cost from token usage.
    
    Args:
        usage: Token usage metadata
        input_price_per_million: Price per million input tokens (defaults to config)
        output_price_per_million: Price per million output tokens (defaults to config)
    
    Returns:
        CostInfo object with calculated costs
    """
    if input_price_per_million is None:
        input_price_per_million = Config.GEMINI_INPUT_PRICE_PER_MILLION
    
    if output_price_per_million is None:
        output_price_per_million = Config.GEMINI_OUTPUT_PRICE_PER_MILLION
    
    # Calculate costs
    prompt_cost = (usage.prompt_tokens / 1_000_000) * input_price_per_million
    completion_cost = (usage.completion_tokens / 1_000_000) * output_price_per_million
    total_cost = prompt_cost + completion_cost
    
    return CostInfo(
        prompt_cost=round(prompt_cost, 6),
        completion_cost=round(completion_cost, 6),
        total_cost=round(total_cost, 6),
        currency="USD"
    )


def calculate_video_cost() -> CostInfo:
    """
    Calculate cost for video generation.
    
    Returns:
        CostInfo object with video generation cost
    """
    cost = Config.VIDEO_GENERATION_COST
    
    return CostInfo(
        prompt_cost=0.0,
        completion_cost=0.0,
        total_cost=round(cost, 6),
        currency="USD"
    )


def get_conversation_cost(conversation: Dict[str, Any]) -> SessionCostInfo:
    """
    Get cumulative cost for a conversation.
    
    Args:
        conversation: Conversation object
    
    Returns:
        SessionCostInfo with cumulative costs
    """
    total_cost = conversation.get('total_cost', 0.0)
    total_tokens = conversation.get('total_tokens', 0)
    
    return SessionCostInfo(
        total_cost=round(total_cost, 6),
        total_tokens=total_tokens,
        currency="USD"
    )


def add_cost_to_conversation(
    current_usage: Optional[UsageMetadata],
    current_cost: Optional[CostInfo],
    conversation: Dict[str, Any]
) -> Tuple[float, int]:
    """
    Add current request cost to conversation totals.
    
    Args:
        current_usage: Token usage for current request
        current_cost: Cost for current request (can be None)
        conversation: Conversation object to update
    
    Returns:
        Tuple of (new_total_cost, new_total_tokens)
    """
    # Get current totals
    prev_total_cost = conversation.get('total_cost', 0.0)
    prev_total_tokens = conversation.get('total_tokens', 0)
    
    # Add current costs (handle None case)
    cost_to_add = current_cost.total_cost if current_cost else 0.0
    new_total_cost = prev_total_cost + cost_to_add
    new_total_tokens = prev_total_tokens + (current_usage.total_tokens if current_usage else 0)
    
    logger.debug(f"Conversation cost updated: ${prev_total_cost:.6f} + ${cost_to_add:.6f} = ${new_total_cost:.6f}")
    
    return (round(new_total_cost, 6), new_total_tokens)

