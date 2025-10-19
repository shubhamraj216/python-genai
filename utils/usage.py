"""Usage tracking utilities."""
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import HTTPException

from config import Config
from utils.logger import get_logger
from common.error_messages import ErrorCode, get_error_response

logger = get_logger("usage")


def _utc_today_iso():
    """Return today's date in ISO format (UTC)."""
    try:
        return datetime.now(timezone.utc).date().isoformat()
    except Exception as e:
        logger.error(f"Error getting current date: {e}")
        # Fallback to a default date format
        return "1970-01-01"


def ensure_user_usage_fields(user_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure user doc has usage tracking fields. Returns the patched doc (but does NOT persist).
    Fields:
      - daily_limit (int)
      - usage_today_date (ISO date str)
      - usage_today_count (int)
    """
    try:
        patched = dict(user_doc)
        if "daily_limit" not in patched:
            patched["daily_limit"] = Config.DEFAULT_DAILY_LIMIT
        if "usage_today_date" not in patched or not patched.get("usage_today_date"):
            patched["usage_today_date"] = _utc_today_iso()
        if "usage_today_count" not in patched:
            patched["usage_today_count"] = 0
        return patched
    except Exception as e:
        logger.error(f"Error ensuring user usage fields: {e}")
        # Return the original doc or a minimal version
        return user_doc if user_doc else {}


def get_user_usage(user_id: str) -> Dict[str, int]:
    """
    Compute usage / counts for a given user.
    Returns dict with generations_today, daily_limit, total_assets, total_images, total_downloads, liked_count
    """
    try:
        # Import here to avoid circular imports
        from auth.services import get_user_by_id
        from database import db
        
        user = get_user_by_id(user_id) or {}
        user = ensure_user_usage_fields(user)

        # ensure today's slate is correct (if date changed, treat count as 0)
        today = _utc_today_iso()
        usage_today = int(user.get("usage_today_count", 0)) if user.get("usage_today_date") == today else 0
        daily_limit = int(user.get("daily_limit", Config.DEFAULT_DAILY_LIMIT))

        # assets owned by user
        try:
            assets = db.find("assets", owner_id=user_id) or []
        except Exception as e:
            logger.warning(f"Error fetching assets for user {user_id}: {e}")
            assets = []
        
        try:
            total_assets = len(assets)
            total_images = sum(1 for a in assets if (a.get("type") or "").startswith("image"))
            total_downloads = sum(int(a.get("downloads", 0) or 0) for a in assets)
            liked_count = sum(1 for a in assets if bool(a.get("liked", False)))
        except Exception as e:
            logger.warning(f"Error calculating asset statistics: {e}")
            total_assets = 0
            total_images = 0
            total_downloads = 0
            liked_count = 0

        return {
            "generations_today": usage_today,
            "daily_limit": daily_limit,
            "total_assets": total_assets,
            "total_images": total_images,
            "total_downloads": total_downloads,
            "liked_count": liked_count,
            "counts": {
                "liked": liked_count,
                "downloaded": sum(1 for a in assets if int(a.get("downloads",0))>0),
                "history": total_assets
            }
        }
    except Exception as e:
        logger.error(f"Error getting user usage: {e}")
        # Return default values
        return {
            "generations_today": 0,
            "daily_limit": Config.DEFAULT_DAILY_LIMIT,
            "total_assets": 0,
            "total_images": 0,
            "total_downloads": 0,
            "liked_count": 0,
            "counts": {
                "liked": 0,
                "downloaded": 0,
                "history": 0
            }
        }


def increment_user_usage(user_id: str, delta: int = 1, persist: bool = True) -> Dict[str, Any]:
    """
    Increment usage_today_count for user (resetting if date changed). Returns updated user doc.
    Will raise HTTPException(403) if increment would exceed daily_limit.
    """
    try:
        # Import here to avoid circular imports
        from auth.services import get_user_by_id, update_user_fields
        
        user = get_user_by_id(user_id)
        if not user:
            logger.error(f"User not found for usage increment: {user_id}")
            raise KeyError("user not found")

        user = ensure_user_usage_fields(user)
        today = _utc_today_iso()
        
        # if day changed, reset to 0
        if user.get("usage_today_date") != today:
            user["usage_today_date"] = today
            user["usage_today_count"] = 0

        current = int(user.get("usage_today_count", 0))
        limit = int(user.get("daily_limit", Config.DEFAULT_DAILY_LIMIT))
        
        if current + delta > limit:
            logger.warning(f"User {user_id} exceeded daily limit: {current + delta}/{limit}")
            message, status_code = get_error_response(ErrorCode.DAILY_LIMIT_REACHED)
            raise HTTPException(status_code=status_code, detail=message)

        # increment
        user["usage_today_count"] = current + delta
        
        # persist
        try:
            update_user_fields(
                user["id"], 
                {
                    "usage_today_date": user["usage_today_date"], 
                    "usage_today_count": user["usage_today_count"], 
                    "daily_limit": user.get("daily_limit", Config.DEFAULT_DAILY_LIMIT)
                }
            )
        except Exception as e:
            logger.error(f"Failed to persist usage update for user {user_id}: {e}")
            # Re-raise to prevent service if we can't track usage
            message, status_code = get_error_response(ErrorCode.DATABASE_ERROR)
            raise HTTPException(status_code=status_code, detail=message)
        
        logger.debug(f"Usage incremented for user {user_id}: {user['usage_today_count']}/{limit}")
        return user
    except KeyError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error incrementing user usage: {e}")
        message, status_code = get_error_response(ErrorCode.DATABASE_ERROR)
        raise HTTPException(status_code=status_code, detail=message)

