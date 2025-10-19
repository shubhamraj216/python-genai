"""Persona management for AI generation (images, videos, etc.)."""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import uuid4

from database import db
from config import Config


# ---------- Default personas template ----------
DEFAULT_PERSONAS = [
    {
        "name": "Artistic Realism",
        "description": (
            "High-detail, realistic yet artistic style. Combines DSLR/medium-format "
            "camera aesthetics with painterly composition. "
            "Includes realistic lighting, accurate anatomy, natural skin/textures, "
            "and cinematic color grading. DSLR configuration: 35mm–85mm prime lens, "
            "f/1.4–f/2.8 aperture, shallow depth of field (bokeh), ISO 100–400, "
            "soft studio or natural golden-hour lighting. "
            "Think cinematic realism fused with fine art photography."
        ),
        "icon": "📸",
        "tags": ["artistic", "realistic", "cinematic", "DSLR", "photography"],
        "is_active": True,  # default active
    },
    {
        "name": "Cartoon Pop",
        "description": (
            "Vibrant cartoon / illustrative style. Bold outlines, saturated colors, "
            "playful proportions, cel-shading or soft shading variants. Great for "
            "stylized characters and background art — like high-quality animation stills."
        ),
        "icon": "🧸",
        "tags": ["cartoon", "illustrative", "bright", "stylized"],
        "is_active": False,
    },
]


# ---------- Persona CRUD functions ----------
def create_persona(owner_id: str, name: str, description: str = "", icon: str = "🎯", tags: Optional[List[str]] = None, is_active: bool = False):
    """Create a new persona for a user."""
    tags = tags or []
    persona = {
        "id": str(uuid4()),
        "owner_id": owner_id,
        "name": name,
        "description": description,
        "icon": icon,
        "tags": tags,
        "is_active": bool(is_active),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    inserted = db.insert_one("personas", persona)
    if Config.PERSIST:
        db.dump_to_files()
    return inserted


def list_personas(owner_id: str):
    """List all personas for a user."""
    return db.find("personas", owner_id=owner_id)


def get_persona(pid: str, owner_id: Optional[str] = None):
    """Get a specific persona."""
    p = db.find_one("personas", {"id": pid}, owner_id=owner_id)
    if not p:
        raise KeyError("persona not found")
    return p


def update_persona(pid: str, patch: Dict[str, Any], owner_id: Optional[str] = None):
    """Update a persona."""
    patch["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.update_one("personas", {"id": pid}, patch, owner_id=owner_id)
    if Config.PERSIST:
        db.dump_to_files()
    return updated


def delete_persona(pid: str, owner_id: Optional[str] = None):
    """Delete a persona."""
    removed = db.delete_one("personas", {"id": pid}, owner_id=owner_id)
    if Config.PERSIST:
        db.dump_to_files()
    return removed


def activate_persona(pid: str, owner_id: str):
    """Activate a persona (and deactivate all others for the user)."""
    # set all other's is_active=False, then set this to True
    # First find existing active and set false (owner-scoped)
    ps = db.find("personas", owner_id=owner_id)
    for p in ps:
        if p.get("is_active"):
            try:
                db.update_one("personas", {"id": p["id"]}, {"is_active": False}, owner_id=owner_id)
            except KeyError:
                pass
    # Activate requested persona
    updated = db.update_one("personas", {"id": pid}, {"is_active": True, "updated_at": datetime.now(timezone.utc).isoformat()}, owner_id=owner_id)
    if Config.PERSIST:
        db.dump_to_files()
    return updated


def get_active_persona(owner_id: str) -> Optional[Dict[str, Any]]:
    """Get the active persona for a user."""
    personas = db.find("personas", {"is_active": True}, owner_id=owner_id)
    return personas[0] if personas else None

