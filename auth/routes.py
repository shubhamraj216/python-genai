"""Authentication routes."""
from datetime import timedelta
from typing import Dict, Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Body, Depends

from auth.models import AuthSignupReq, AuthLoginReq
from auth.services import (
    get_user_by_email,
    get_user_by_id,
    create_user,
    authenticate_user,
    create_access_token,
    update_user_fields,
    get_current_user
)
from config import Config
from utils.usage import ensure_user_usage_fields, _utc_today_iso
from utils.logger import get_logger
from common.error_messages import ErrorCode, get_error_response

logger = get_logger("auth.routes")
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup")
def signup(req: AuthSignupReq = Body(...)):
    """Sign up a new user."""
    try:
        logger.info(f"Signup attempt for email: {req.email}")
        
        if get_user_by_email(req.email):
            message, status_code = get_error_response(ErrorCode.EMAIL_IN_USE)
            raise HTTPException(status_code=status_code, detail=message)
        
        try:
            # pass first/last into create_user
            user = create_user(req.email, req.password, is_guest=False, first_name=req.first_name or "", last_name=req.last_name or "")
        except ValueError as e:
            logger.warning(f"Failed to create user: {e}")
            message, status_code = get_error_response(ErrorCode.INVALID_PARAMETER)
            raise HTTPException(status_code=status_code, detail=message)

        # create token payload including name for convenience
        try:
            token = create_access_token({"sub": user["id"], "email": user["email"], "is_guest": False})
        except Exception as e:
            logger.error(f"Failed to create token for new user: {e}")
            message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
            raise HTTPException(status_code=status_code, detail=message)
        
        logger.info(f"User created successfully: {user['id']}")
        
        # return both token and user profile (frontend will use this to show name)
        return {
            "access_token": token, 
            "token_type": "bearer", 
            "user": { 
                "id": user["id"], 
                "email": user["email"], 
                "first_name": user.get("first_name",""), 
                "last_name": user.get("last_name","") 
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during signup: {e}")
        message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
        raise HTTPException(status_code=status_code, detail=message)


@router.get("/me")
def me(user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user profile."""
    try:
        # don't return password hash
        u = get_user_by_id(user["id"])
        if not u:
            message, status_code = get_error_response(ErrorCode.USER_NOT_FOUND)
            raise HTTPException(status_code=status_code, detail=message)
        
        try:
            u = ensure_user_usage_fields(u)
        except Exception as e:
            logger.warning(f"Failed to ensure usage fields for user {user['id']}: {e}")
            # Continue with partial data
        
        return {
            "id": u["id"],
            "email": u["email"],
            "first_name": u.get("first_name", ""),
            "last_name": u.get("last_name", ""),
            "is_guest": u.get("is_guest", False),
            "guest_quota": u.get("guest_quota", 0),
            "daily_limit": int(u.get("daily_limit", Config.DEFAULT_DAILY_LIMIT)),
            "usage_today_count": int(u.get("usage_today_count", 0)) if u.get("usage_today_date") == _utc_today_iso() else 0
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        message, status_code = get_error_response(ErrorCode.DATABASE_ERROR)
        raise HTTPException(status_code=status_code, detail=message)


@router.post("/login")
def login(req: AuthLoginReq = Body(...)):
    """Login user."""
    try:
        logger.info(f"Login attempt for email: {req.email}")
        
        try:
            user = authenticate_user(req.email, req.password)
        except ValueError as e:
            logger.warning(f"Authentication failed for {req.email}: {e}")
            message, status_code = get_error_response(ErrorCode.INVALID_CREDENTIALS)
            raise HTTPException(status_code=status_code, detail=message)
        
        try:
            token = create_access_token({"sub": user["id"], "email": user["email"], "is_guest": user.get("is_guest", False)})
        except Exception as e:
            logger.error(f"Failed to create token for user {user['id']}: {e}")
            message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
            raise HTTPException(status_code=status_code, detail=message)
        
        logger.info(f"Login successful for user: {user['id']}")
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}")
        message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
        raise HTTPException(status_code=status_code, detail=message)


@router.post("/guest")
def create_guest():
    """Create guest user."""
    try:
        logger.info("Creating guest user")
        
        uid = str(uuid4())
        guest_email = f"guest+{uid}@local"
        
        try:
            user = create_user(guest_email, password="", is_guest=True, guest_quota=Config.GUEST_QUOTA_DEFAULT)
        except Exception as e:
            logger.error(f"Failed to create guest user: {e}")
            message, status_code = get_error_response(ErrorCode.OPERATION_FAILED)
            raise HTTPException(status_code=status_code, detail=message)
        
        try:
            token = create_access_token(
                {"sub": user["id"], "email": user["email"], "is_guest": True},
                expires_delta=timedelta(minutes=Config.GUEST_TOKEN_EXPIRE_MINUTES)
            )
        except Exception as e:
            logger.error(f"Failed to create token for guest user: {e}")
            message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
            raise HTTPException(status_code=status_code, detail=message)
        
        logger.info(f"Guest user created: {user['id']}")
        return {"access_token": token, "expires_in_minutes": Config.GUEST_TOKEN_EXPIRE_MINUTES, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating guest user: {e}")
        message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
        raise HTTPException(status_code=status_code, detail=message)


@router.post("/forgot-password")
def forgot_password(email: str = Body(...)):
    """Request password reset."""
    try:
        logger.info(f"Password reset request for: {email}")
        
        try:
            user = get_user_by_email(email)
        except Exception as e:
            logger.error(f"Error looking up user for password reset: {e}")
            # don't reveal whether email exists
            return {"ok": True}
        
        if not user:
            # don't reveal whether email exists
            return {"ok": True}
        
        rt = str(uuid4())
        
        try:
            update_user_fields(user["id"], {"reset_token": rt})
        except Exception as e:
            logger.error(f"Failed to update reset token for user {user['id']}: {e}")
            message, status_code = get_error_response(ErrorCode.DATABASE_ERROR)
            raise HTTPException(status_code=status_code, detail=message)
        
        # In prod: send email. Here return token for testing.
        logger.info(f"Password reset token created for user: {user['id']}")
        return {"ok": True, "reset_token": rt}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during password reset: {e}")
        message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
        raise HTTPException(status_code=status_code, detail=message)

