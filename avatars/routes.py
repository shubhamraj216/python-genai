"""Avatar management API routes."""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from auth.services import get_current_user
from avatars.services import (
    save_avatar_image,
    get_user_avatars,
    get_avatar_by_id,
    delete_avatar,
    set_default_avatar
)
from avatars.models import (
    AvatarUploadResponse,
    AvatarListResponse,
    AvatarMetadata,
    AvatarDeleteResponse
)
from utils.logger import get_logger

logger = get_logger("avatars.routes")
router = APIRouter(prefix="/api/avatars", tags=["avatars"])


@router.post("/upload", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    name: str = Form(...),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Upload a new avatar image.
    
    Args:
        file: Image file (multipart/form-data)
        name: User-friendly name for the avatar
        user: Current authenticated user
    
    Returns:
        Avatar metadata with ID and URL
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read file data
        try:
            image_data = await file.read()
        except Exception as e:
            logger.error(f"Failed to read uploaded file: {e}")
            raise HTTPException(status_code=400, detail="Failed to read uploaded file")
        
        # Validate file size (e.g., max 10MB)
        max_size = 10 * 1024 * 1024  # 10MB
        if len(image_data) > max_size:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Save avatar
        try:
            avatar = save_avatar_image(
                owner_id=user["id"],
                image_data=image_data,
                name=name,
                mime_type=file.content_type
            )
        except RuntimeError as e:
            logger.error(f"Failed to save avatar: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        
        logger.info(f"Avatar uploaded successfully: {avatar['id']} by user {user['id']}")
        
        return AvatarUploadResponse(
            avatar_id=avatar["id"],
            name=avatar["name"],
            url=avatar["url"],
            message="Avatar uploaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error uploading avatar: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload avatar")


@router.get("", response_model=AvatarListResponse)
def list_avatars(user: Dict[str, Any] = Depends(get_current_user)):
    """
    List all avatars for the current user.
    
    Returns:
        List of avatar metadata
    """
    try:
        avatars = get_user_avatars(user["id"])
        
        # Convert to Pydantic models
        avatar_models = [AvatarMetadata(**av) for av in avatars]
        
        logger.info(f"Listed {len(avatars)} avatars for user {user['id']}")
        
        return AvatarListResponse(
            avatars=avatar_models,
            count=len(avatars)
        )
        
    except Exception as e:
        logger.error(f"Failed to list avatars: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve avatars")


@router.get("/{avatar_id}", response_model=AvatarMetadata)
def get_avatar(
    avatar_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get specific avatar details.
    
    Args:
        avatar_id: Avatar identifier
    
    Returns:
        Avatar metadata
    """
    try:
        avatar = get_avatar_by_id(avatar_id, user["id"])
        
        if not avatar:
            raise HTTPException(status_code=404, detail="Avatar not found")
        
        return AvatarMetadata(**avatar)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get avatar {avatar_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve avatar")


@router.delete("/{avatar_id}", response_model=AvatarDeleteResponse)
def delete_avatar_endpoint(
    avatar_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete an avatar.
    
    Args:
        avatar_id: Avatar identifier
    
    Returns:
        Deletion confirmation
    """
    try:
        deleted = delete_avatar(avatar_id, user["id"])
        
        logger.info(f"Avatar {avatar_id} deleted by user {user['id']}")
        
        return AvatarDeleteResponse(
            avatar_id=avatar_id,
            message="Avatar deleted successfully"
        )
        
    except KeyError:
        raise HTTPException(status_code=404, detail="Avatar not found")
    except RuntimeError as e:
        logger.error(f"Failed to delete avatar: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error deleting avatar: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete avatar")


@router.post("/{avatar_id}/set-default", response_model=AvatarMetadata)
def set_default_avatar_endpoint(
    avatar_id: str,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Set an avatar as the user's default avatar.
    
    Args:
        avatar_id: Avatar identifier
    
    Returns:
        Updated avatar metadata
    """
    try:
        updated = set_default_avatar(avatar_id, user["id"])
        
        logger.info(f"Avatar {avatar_id} set as default for user {user['id']}")
        
        return AvatarMetadata(**updated)
        
    except KeyError:
        raise HTTPException(status_code=404, detail="Avatar not found")
    except RuntimeError as e:
        logger.error(f"Failed to set default avatar: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error setting default avatar: {e}")
        raise HTTPException(status_code=500, detail="Failed to set default avatar")

