"""Avatar service functions for CRUD operations and image loading."""
import os
import base64
import mimetypes
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import uuid4

from config import Config
from database.db import db
from utils.logger import get_logger

logger = get_logger("avatars.services")


def save_avatar_image(
    owner_id: str,
    image_data: bytes,
    name: str,
    mime_type: str
) -> Dict[str, Any]:
    """
    Save uploaded avatar image to filesystem and create database record.
    
    Args:
        owner_id: User ID who owns the avatar
        image_data: Raw image bytes
        name: User-friendly name for the avatar
        mime_type: Image MIME type
    
    Returns:
        Avatar metadata dictionary
    """
    try:
        # Generate unique avatar ID
        avatar_id = str(uuid4())
        
        # Determine file extension
        extension = mimetypes.guess_extension(mime_type) or ".png"
        if extension == ".jpe":
            extension = ".jpg"
        
        # Create user-specific avatar directory
        user_avatar_dir = os.path.join(Config.AVATARS_DIR, owner_id)
        os.makedirs(user_avatar_dir, exist_ok=True)
        
        # Save image file
        filename = f"{avatar_id}{extension}"
        file_path = os.path.join(user_avatar_dir, filename)
        
        with open(file_path, "wb") as f:
            f.write(image_data)
        
        # Create relative path and URL
        relative_path = f"avatars/{owner_id}/{filename}"
        url = f"/assets/{relative_path}"
        
        # Create database record
        avatar_doc = {
            "id": avatar_id,
            "owner_id": owner_id,
            "name": name,
            "file_path": relative_path,
            "url": url,
            "mime_type": mime_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_default": False
        }
        
        db.insert_one("avatars", avatar_doc)
        db.dump_to_files()
        
        logger.info(f"Saved avatar {avatar_id} for user {owner_id}: {name}")
        
        return avatar_doc
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to save avatar file: {e}")
        raise RuntimeError(f"Failed to save avatar image: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error saving avatar: {e}")
        raise RuntimeError("Failed to save avatar")


def load_avatar_as_base64(avatar_id: str, owner_id: str) -> Dict[str, str]:
    """
    Load avatar image and convert to base64 for use in generation requests.
    
    Args:
        avatar_id: Avatar identifier
        owner_id: User ID (for ownership validation)
    
    Returns:
        Dictionary with mime_type and base64-encoded data
        Format: {"mime_type": "image/png", "data": "base64..."}
    
    Raises:
        RuntimeError: If avatar not found or not accessible
    """
    try:
        # Fetch avatar metadata from database
        avatar = db.find_one("avatars", {"id": avatar_id}, owner_id=owner_id)
        
        if not avatar:
            logger.warning(f"Avatar {avatar_id} not found for user {owner_id}")
            raise RuntimeError(f"Avatar {avatar_id} not found or not accessible")
        
        # Construct full file path
        file_path = os.path.join("assets", avatar["file_path"])
        
        if not os.path.exists(file_path):
            logger.error(f"Avatar file not found: {file_path}")
            raise RuntimeError(f"Avatar file not found: {avatar_id}")
        
        # Read and encode image
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        
        encoded_data = base64.b64encode(image_bytes).decode("utf-8")
        
        logger.info(f"Loaded avatar {avatar_id} ({avatar['mime_type']}, {len(image_bytes)} bytes)")
        
        return {
            "mime_type": avatar["mime_type"],
            "data": encoded_data
        }
        
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading avatar {avatar_id}: {e}")
        raise RuntimeError(f"Failed to load avatar: {str(e)}")


def get_user_avatars(owner_id: str) -> List[Dict[str, Any]]:
    """
    Get all avatars for a user.
    
    Args:
        owner_id: User ID
    
    Returns:
        List of avatar metadata dictionaries
    """
    try:
        avatars = db.find("avatars", owner_id=owner_id)
        logger.info(f"Retrieved {len(avatars)} avatars for user {owner_id}")
        return avatars
    except Exception as e:
        logger.error(f"Failed to retrieve avatars for user {owner_id}: {e}")
        raise RuntimeError("Failed to retrieve avatars")


def get_avatar_by_id(avatar_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
    """
    Get specific avatar by ID.
    
    Args:
        avatar_id: Avatar identifier
        owner_id: User ID (for ownership validation)
    
    Returns:
        Avatar metadata dictionary or None if not found
    """
    try:
        avatar = db.find_one("avatars", {"id": avatar_id}, owner_id=owner_id)
        return avatar
    except Exception as e:
        logger.error(f"Failed to retrieve avatar {avatar_id}: {e}")
        raise RuntimeError("Failed to retrieve avatar")


def delete_avatar(avatar_id: str, owner_id: str) -> Dict[str, Any]:
    """
    Delete an avatar (both file and database record).
    
    Args:
        avatar_id: Avatar identifier
        owner_id: User ID (for ownership validation)
    
    Returns:
        Deleted avatar metadata
    
    Raises:
        KeyError: If avatar not found
        RuntimeError: If deletion fails
    """
    try:
        # Get avatar metadata first
        avatar = db.find_one("avatars", {"id": avatar_id}, owner_id=owner_id)
        
        if not avatar:
            logger.warning(f"Avatar {avatar_id} not found for user {owner_id}")
            raise KeyError("Avatar not found")
        
        # Delete file if it exists
        file_path = os.path.join("assets", avatar["file_path"])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Deleted avatar file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to delete avatar file {file_path}: {e}")
                # Continue with database deletion even if file deletion fails
        
        # Delete from database
        deleted = db.delete_one("avatars", {"id": avatar_id}, owner_id=owner_id)
        db.dump_to_files()
        
        logger.info(f"Deleted avatar {avatar_id} for user {owner_id}")
        
        return deleted
        
    except KeyError:
        raise
    except Exception as e:
        logger.error(f"Failed to delete avatar {avatar_id}: {e}")
        raise RuntimeError("Failed to delete avatar")


def set_default_avatar(avatar_id: str, owner_id: str) -> Dict[str, Any]:
    """
    Set an avatar as the user's default avatar.
    Unsets any previously default avatar.
    
    Args:
        avatar_id: Avatar identifier
        owner_id: User ID
    
    Returns:
        Updated avatar metadata
    """
    try:
        # Verify avatar exists
        avatar = db.find_one("avatars", {"id": avatar_id}, owner_id=owner_id)
        if not avatar:
            raise KeyError("Avatar not found")
        
        # Unset all other defaults for this user
        all_user_avatars = db.find("avatars", owner_id=owner_id)
        for av in all_user_avatars:
            if av.get("is_default"):
                db.update_one("avatars", {"id": av["id"]}, {"is_default": False}, owner_id=owner_id)
        
        # Set this one as default
        updated = db.update_one("avatars", {"id": avatar_id}, {"is_default": True}, owner_id=owner_id)
        db.dump_to_files()
        
        logger.info(f"Set avatar {avatar_id} as default for user {owner_id}")
        
        return updated
        
    except KeyError:
        raise
    except Exception as e:
        logger.error(f"Failed to set default avatar {avatar_id}: {e}")
        raise RuntimeError("Failed to set default avatar")

