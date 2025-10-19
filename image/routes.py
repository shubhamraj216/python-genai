"""Image generation and persona routes."""
from datetime import datetime, timezone
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Body, Depends
from zoneinfo import ZoneInfo

from auth.services import get_current_user, get_user_by_id, update_user_fields
from image.models import GenerateRequest
from image.services import call_gemini_generate_stream_and_save
from common.personas import (
    list_personas,
    create_persona,
    update_persona,
    delete_persona,
    activate_persona
)
from conversations.services import create_conversation, get_conversation, append_message_to_conversation
from utils.usage import ensure_user_usage_fields, increment_user_usage, _utc_today_iso
from utils.logger import get_logger
from config import Config

logger = get_logger("image")
router = APIRouter(tags=["image"])


@router.post("/api/generate")
def generate(req: GenerateRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Generate images from prompt using Gemini.
    
    Accepts:
      { prompt: "...", conversation_id?: "..." }

    Behavior:
      - append a user message to conversation (create conv if missing)
      - call Gemini -> saves inline asset files & asset metadata (owner-scoped)
      - append assistant message (with saved_assets) to conversation
      - increment usage only after successful generation
    """
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt required")

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

    # Extract conversation history from the conversation object
    conversation_history = conv.get("messages", [])
    logger.info(f"Using conversation {conv_id} with {len(conversation_history)} existing messages")
    
    # Build and append the user message first (persist immediately)
    user_msg = {
        "id": str(uuid4()),
        "role": "user",
        "content": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        append_message_to_conversation(conv_id, user_msg, owner_id=user["id"])
    except KeyError:
        raise HTTPException(status_code=500, detail="failed to append user message to conversation")

    # Call Gemini with conversation history and save assets (owner-aware, with persona integration)
    try:
        logger.info(f"Starting image generation for user {user['id']} with prompt: {prompt[:50]}...")
        if req.avatar_id:
            logger.info(f"Using avatar {req.avatar_id} for character consistency")
        result = call_gemini_generate_stream_and_save(
            prompt, 
            owner_id=user["id"],
            conversation_history=conversation_history,
            avatar_id=req.avatar_id
        )
        assistant_text = result.content
        saved_assets = result.assets or []
        logger.info(f"Generated {len(saved_assets)} asset(s) for user {user['id']}")
    except Exception as e:
        # generation failed: user message retained. Return error to client.
        logger.error(f"Image generation failed for user {user['id']}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"generation error: {str(e)}")

    # Increment usage only after successful generation
    try:
        increment_user_usage(user["id"], delta=1)
    except HTTPException:
        # concurrent limit reached — defensive; we already saved assets and messages,
        # but respond with 403 to the client to highlight limit.
        raise HTTPException(status_code=403, detail="Daily usage limit reached (concurrent)")

    if not assistant_text:
        assistant_text = f"I've created assets based on your prompt: \"{prompt}\"."

    # Build assistant message (with assets)
    assistant_msg = {
        "id": str(uuid4()),
        "role": "assistant",
        "content": assistant_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assets": saved_assets,  # each saved asset = {id, type, url, prompt}
    }

    # Append assistant message to conversation
    try:
        append_message_to_conversation(conv_id, assistant_msg, owner_id=user["id"])
    except KeyError:
        # If append fails, we log and continue — assets + user message already persisted.
        print(f"warning: failed to append assistant message to conversation {conv_id}")

    # Return assistant message + conversation id so frontend can remain bound to conversation
    return {"message": assistant_msg, "conversation_id": conv_id}


# ---------- Persona endpoints ----------
@router.get("/api/personas")
def api_list_personas(user: Dict[str, Any] = Depends(get_current_user)):
    """List all personas for current user."""
    ps = list_personas(user["id"])
    return {"personas": ps}


@router.post("/api/personas")
def api_create_persona(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Create a new persona."""
    try:
        name = str(payload["name"])
    except Exception:
        raise HTTPException(status_code=400, detail="name is required")
    description = str(payload.get("description", ""))
    icon = str(payload.get("icon", "🎯"))
    tags = list(payload.get("tags", []))
    persona = create_persona(user["id"], name, description=description, icon=icon, tags=tags, is_active=bool(payload.get("is_active", False)))
    return persona


@router.put("/api/personas/{persona_id}")
def api_update_persona(persona_id: str = Path(...), payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Update a persona."""
    try:
        updated = update_persona(persona_id, payload, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")


@router.delete("/api/personas/{persona_id}")
def api_delete_persona(persona_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a persona."""
    try:
        # ensure at least one persona remains
        ps = list_personas(user["id"])
        if len(ps) <= 1:
            raise HTTPException(status_code=400, detail="At least one persona must exist")
        removed = delete_persona(persona_id, owner_id=user["id"])
        return {"deleted": True, "persona": removed}
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")


@router.post("/api/personas/{persona_id}/activate")
def api_activate_persona(persona_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Activate a persona."""
    try:
        updated = activate_persona(persona_id, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="persona not found")

