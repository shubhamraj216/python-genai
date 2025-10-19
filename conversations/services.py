"""Conversation management services."""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import uuid4

from database import db
from config import Config


def create_conversation(owner_id: str, title: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a conversation container. Fields:
      id, owner_id, title, created_at, updated_at, messages (list), total_cost, total_tokens
    """
    now = datetime.now(timezone.utc).isoformat()
    conv = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "title": title or f"Conversation {now}",
        "created_at": now,
        "updated_at": now,
        "messages": [],  # messages: { id, role, content, timestamp, assets?: [{id,url,prompt}] }
        "total_cost": 0.0,  # Cumulative cost in USD
        "total_tokens": 0,  # Cumulative token count
    }
    inserted = db.insert_one("conversations", conv)
    if Config.PERSIST:
        db.dump_to_files()
    return inserted


def list_conversations(owner_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Return conversations for owner sorted by updated_at desc (recent first).
    """
    convs = db.find("conversations", owner_id=owner_id) or []
    convs_sorted = sorted(convs, key=lambda c: c.get("updated_at", ""), reverse=True)
    return convs_sorted[:limit]


def get_conversation(conv_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    """Get a specific conversation."""
    c = db.find_one("conversations", {"id": conv_id}, owner_id=owner_id)
    if not c:
        raise KeyError("conversation not found")
    return c


def append_message_to_conversation(conv_id: str, message: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Append message to conversation.messages and update updated_at.
    message should contain: id, role ('user'|'assistant'), content, timestamp, optional assets
    """
    try:
        conv = db.find_one("conversations", {"id": conv_id}, owner_id=owner_id)
        if not conv:
            raise KeyError("conversation not found")
        msgs = conv.get("messages", [])
        msgs.append(message)
        now = datetime.now(timezone.utc).isoformat()
        updated = db.update_one("conversations", {"id": conv_id}, {"messages": msgs, "updated_at": now}, owner_id=owner_id)
        if Config.PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise


def update_conversation_cost(conv_id: str, total_cost: float, total_tokens: int, owner_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Update conversation cost and token totals.
    
    Args:
        conv_id: Conversation ID
        total_cost: New total cost in USD
        total_tokens: New total token count
        owner_id: Optional owner ID for verification
    
    Returns:
        Updated conversation object
    """
    try:
        conv = db.find_one("conversations", {"id": conv_id}, owner_id=owner_id)
        if not conv:
            raise KeyError("conversation not found")
        
        updated = db.update_one(
            "conversations",
            {"id": conv_id},
            {
                "total_cost": total_cost,
                "total_tokens": total_tokens,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            owner_id=owner_id
        )
        if Config.PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise

