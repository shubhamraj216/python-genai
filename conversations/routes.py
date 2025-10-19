"""Conversation routes."""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Path, Body, Depends

from auth.services import get_current_user
from conversations.services import create_conversation, list_conversations, get_conversation

router = APIRouter(prefix="/api", tags=["conversations"])


@router.post("/conversations")
def api_create_conversation(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    """
    Create a new conversation for current user.
    payload: { title?: string }
    returns conversation object
    """
    title = str(payload.get("title")) if payload else None
    conv = create_conversation(owner_id=user["id"], title=title)
    return conv


@router.get("/conversations")
def api_list_conversations(user: Dict[str, Any] = Depends(get_current_user), limit: int = 20):
    """
    List recent conversations for current user (most recent first).
    """
    convs = list_conversations(owner_id=user["id"], limit=limit)
    # Return shallow metadata (no messages) to keep response small
    shallow = [{
        "id": c["id"],
        "title": c.get("title"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "message_count": len(c.get("messages", []))
    } for c in convs]
    return {"conversations": shallow}


@router.get("/recent-conversations")
def api_recent_conversations(user: Dict[str, Any] = Depends(get_current_user), limit: int = 5):
    """
    List conversations for current user updated within the last 24 hours (most recent first).
    """
    convs = list_conversations(owner_id=user["id"], limit=limit)  # get more, then filter
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    filtered = []
    for c in convs:
        try:
            updated_at = datetime.fromisoformat(c.get("updated_at"))
        except Exception:
            continue
        if updated_at >= cutoff:
            filtered.append(c)

    # Sort after filtering (desc by updated_at)
    convs_sorted = sorted(filtered, key=lambda c: c.get("updated_at", ""), reverse=True)

    shallow = [{
        "id": c["id"],
        "title": c.get("title"),
        "created_at": c.get("created_at"),
        "updated_at": c.get("updated_at"),
        "message_count": len(c.get("messages", []))
    } for c in convs_sorted[:limit]]

    return {"conversations": shallow}


@router.get("/conversations/{conv_id}")
def api_get_conversation(conv_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Get a specific conversation with all messages."""
    try:
        conv = get_conversation(conv_id, owner_id=user["id"])
        return conv
    except KeyError:
        raise HTTPException(status_code=404, detail="conversation not found")

