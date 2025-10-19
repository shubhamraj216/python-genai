"""Asset metadata management services."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from database import db
from config import Config


def add_asset_metadata(aid: str, type_: str, url: str, prompt: str, owner_id: Optional[str] = None):
    """Add metadata for a generated asset."""
    # No-op if same id exists for same owner
    existing = db.find_one("assets", {"id": aid}, owner_id=owner_id)
    if existing:
        return existing
    new = {
        "id": aid,
        "type": type_,
        "url": url,
        "prompt": prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "liked": False,
        "downloads": 0,
        "owner_id": owner_id,
    }
    ins = db.insert_one("assets", new)
    if Config.PERSIST:
        db.dump_to_files()
    return ins


def update_asset_field(asset_id: str, patch: Dict[str, Any], owner_id: Optional[str] = None) -> Dict[str, Any]:
    """Update asset metadata fields."""
    try:
        updated = db.update_one("assets", {"id": asset_id}, patch, owner_id=owner_id)
        if Config.PERSIST:
            db.dump_to_files()
        return updated
    except KeyError:
        raise KeyError("asset not found")


def remove_asset_metadata_only(asset_id: str, owner_id: Optional[str] = None) -> Dict[str, Any]:
    """Remove asset metadata (does not delete the actual file)."""
    try:
        removed = db.delete_one("assets", {"id": asset_id}, owner_id=owner_id)
        if Config.PERSIST:
            db.dump_to_files()
        return removed
    except KeyError:
        raise KeyError("asset not found")

