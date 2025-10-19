"""Asset routes."""
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Path, Body, Depends

from auth.services import get_current_user
from assets.services import add_asset_metadata, update_asset_field, remove_asset_metadata_only
from database import db
from utils.usage import get_user_usage

router = APIRouter(prefix="/api", tags=["assets"])


@router.get("/usage")
def usage(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns computed usage and counts for the current user.
    Example:
    {
      "generations_today": 0,
      "daily_limit": 25,
      "total_assets": 0,
      "total_images": 0,
      "total_downloads": 0,
      "liked_count": 0,
      "counts": { "liked": 0, "downloaded": 0, "history": 0 }
    }
    """
    try:
        from auth.services import get_user_by_id
        u = get_user_by_id(user["id"])
        if not u:
            raise HTTPException(status_code=404, detail="user not found")
        return get_user_usage(user["id"])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to compute usage: {str(e)}")


@router.get("/assets")
def list_assets(user: Dict[str, Any] = Depends(get_current_user)):
    """List all assets for current user."""
    assets = db.find("assets", owner_id=user["id"]) or []
    return {"assets": assets}


@router.post("/assets")
def create_asset(payload: Dict[str, Any] = Body(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Create a new asset metadata entry."""
    try:
        aid = str(payload.get("id", str(uuid4())))
        atype = str(payload["type"])
        url = str(payload["url"])
        prompt = str(payload.get("prompt", ""))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")

    added = add_asset_metadata(aid, atype, url, prompt, owner_id=user["id"])
    return added


@router.post("/assets/{asset_id}/toggle-like")
def toggle_like(asset_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Toggle like status for an asset."""
    try:
        # find asset owned by user
        a = db.find_one("assets", {"id": asset_id}, owner_id=user["id"])
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        new_liked = not bool(a.get("liked", False))
        if not new_liked:
            removed = remove_asset_metadata_only(asset_id, owner_id=user["id"])
            return {"deleted": True, "id": asset_id}
        else:
            updated = update_asset_field(asset_id, {"liked": True}, owner_id=user["id"])
            return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")


@router.post("/assets/{asset_id}/increment-download")
def increment_download(asset_id: str = Path(...), user: Dict[str, Any] = Depends(get_current_user)):
    """Increment download count for an asset."""
    try:
        a = db.find_one("assets", {"id": asset_id}, owner_id=user["id"])
        if not a:
            raise HTTPException(status_code=404, detail="asset not found")
        new_downloads = int(a.get("downloads", 0)) + 1
        updated = update_asset_field(asset_id, {"downloads": new_downloads}, owner_id=user["id"])
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="asset not found")

