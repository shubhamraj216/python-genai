"""Authentication services - user management, JWT, password hashing."""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from uuid import uuid4

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import jwt, JWTError

from config import Config
from database import db
from utils.usage import _utc_today_iso
from utils.logger import get_logger
from common.error_messages import ErrorCode, get_error_response

logger = get_logger("auth.services")

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


# ---------- User CRUD functions ----------
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email address."""
    try:
        return db.find_one("users", {"email": email})
    except Exception as e:
        logger.error(f"Error finding user by email: {e}")
        return None


def get_user_by_id(uid: str) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    try:
        return db.find_one("users", {"id": uid})
    except Exception as e:
        logger.error(f"Error finding user by ID: {e}")
        return None


def create_user(email: str, password: str, is_guest: bool = False, guest_quota: Optional[int] = None, first_name: Optional[str] = None, last_name: Optional[str] = None) -> Dict[str, Any]:
    """Create a new user."""
    try:
        if get_user_by_email(email):
            raise ValueError("email exists")
        
        uid = str(uuid4())
        
        # Hash password with error handling
        try:
            hashed = pwd_context.hash(password) if password else ""
        except Exception as e:
            logger.error(f"Error hashing password: {e}")
            raise ValueError("Failed to secure password")
        
        now = datetime.now(timezone.utc).isoformat()
        user = {
            "id": uid,
            "email": email,
            "password_hash": hashed,
            "is_guest": bool(is_guest),
            "guest_quota": int(guest_quota) if guest_quota is not None else (Config.GUEST_QUOTA_DEFAULT if is_guest else 0),
            "created_at": now,
            "reset_token": None,
            "first_name": first_name or "",
            "last_name": last_name or "",
            "daily_limit": Config.DEFAULT_DAILY_LIMIT,
            "usage_today_date": _utc_today_iso(),
            "usage_today_count": 0,
        }
        
        try:
            inserted = db.insert_one("users", user)
        except Exception as e:
            logger.error(f"Error inserting user into database: {e}")
            raise ValueError("Failed to create user account")

        # create default personas for the new user
        try:
            from common.personas import DEFAULT_PERSONAS, create_persona
            for i, tmpl in enumerate(DEFAULT_PERSONAS):
                try:
                    create_persona(
                        owner_id=inserted["id"],
                        name=tmpl["name"],
                        description=tmpl["description"],
                        icon=tmpl.get("icon", "🎯"),
                        tags=tmpl.get("tags", []),
                        is_active=bool(tmpl.get("is_active")) if i == 0 else False
                    )
                except Exception as persona_error:
                    logger.warning(f"Failed to create default persona '{tmpl.get('name')}': {persona_error}")
                    # Continue even if persona creation fails
        except Exception as e:
            logger.warning(f"Failed to create default personas: {e}")
            # Don't fail user creation if personas fail
        
        if Config.PERSIST:
            try:
                db.dump_to_files()
            except Exception as e:
                logger.warning(f"Failed to persist user data: {e}")
                # Don't fail user creation if persistence fails
        
        return inserted
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating user: {e}")
        raise ValueError(f"Failed to create user: {str(e)}")


def update_user_fields(uid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """Update user fields."""
    try:
        updated = db.update_one("users", {"id": uid}, patch)
        if Config.PERSIST:
            try:
                db.dump_to_files()
            except Exception as e:
                logger.warning(f"Failed to persist user update: {e}")
                # Don't fail the update if persistence fails
        return updated
    except KeyError:
        raise KeyError("user not found")
    except Exception as e:
        logger.error(f"Error updating user fields: {e}")
        raise RuntimeError("Failed to update user")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        if not hashed:
            return False
        return pwd_context.verify(plain, hashed)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """Authenticate user with email and password."""
    try:
        user = get_user_by_email(email)
        if not user:
            raise ValueError("user not found")
        if not verify_password(password, user.get("password_hash", "")):
            raise ValueError("invalid credentials")
        return user
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error authenticating user: {e}")
        raise ValueError("Authentication failed")


# ---------- JWT functions ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token."""
    try:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(days=Config.ACCESS_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": int(expire.timestamp())})
        token = jwt.encode(to_encode, Config.get_secret_key(), algorithm=Config.ALGORITHM)
        return token
    except Exception as e:
        logger.error(f"Error creating access token: {e}")
        raise RuntimeError("Failed to create authentication token")


def decode_token(token: str) -> dict:
    """Decode JWT token."""
    try:
        payload = jwt.decode(token, Config.get_secret_key(), algorithms=[Config.ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        message, status_code = get_error_response(ErrorCode.INVALID_TOKEN)
        raise HTTPException(status_code=status_code, detail=message)
    except Exception as e:
        logger.error(f"Error decoding token: {e}")
        message, status_code = get_error_response(ErrorCode.INVALID_TOKEN)
        raise HTTPException(status_code=status_code, detail=message)


# ---------- Auth dependency ----------
def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    """Get current authenticated user from JWT token."""
    try:
        token = creds.credentials
        payload = decode_token(token)
        uid = payload.get("sub")
        if not uid:
            message, status_code = get_error_response(ErrorCode.INVALID_TOKEN)
            raise HTTPException(status_code=status_code, detail=message)
        user = get_user_by_id(uid)
        if not user:
            message, status_code = get_error_response(ErrorCode.USER_NOT_FOUND)
            raise HTTPException(status_code=status_code, detail=message)
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        message, status_code = get_error_response(ErrorCode.INVALID_TOKEN)
        raise HTTPException(status_code=status_code, detail=message)

