"""
Configuration module - loads all settings from environment variables.
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
try:
    load_dotenv()
except Exception as e:
    print(f"Warning: Failed to load .env file: {e}")
    print("Continuing with environment variables or defaults...")


class Config:
    """Application configuration loaded from environment variables."""
    
    @staticmethod
    def _get_int(key: str, default: int) -> int:
        """Safely parse integer environment variable."""
        try:
            return int(os.getenv(key, str(default)))
        except (ValueError, TypeError) as e:
            print(f"Warning: Invalid integer for {key}, using default {default}: {e}")
            return default
    
    @staticmethod
    def _get_float(key: str, default: float) -> float:
        """Safely parse float environment variable."""
        try:
            return float(os.getenv(key, str(default)))
        except (ValueError, TypeError) as e:
            print(f"Warning: Invalid float for {key}, using default {default}: {e}")
            return default
    
    @staticmethod
    def _get_bool(key: str, default: bool) -> bool:
        """Safely parse boolean environment variable."""
        try:
            value = os.getenv(key, str(default)).lower()
            return value in ("true", "1", "yes", "on")
        except Exception as e:
            print(f"Warning: Invalid boolean for {key}, using default {default}: {e}")
            return default
    
    # JWT & Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_DAYS: int = _get_int.__func__("ACCESS_TOKEN_EXPIRE_DAYS", 30)
    
    # Gemini API
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-image-preview")
    GEMINI_VIDEO_MODEL: str = os.getenv("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview")
    
    # File Storage
    ASSETS_DIR: str = os.getenv("ASSETS_DIR", "assets/generated")
    VIDEOS_DIR: str = os.getenv("VIDEOS_DIR", "assets/generated/videos")
    AVATARS_DIR: str = os.getenv("AVATARS_DIR", "assets/avatars")
    
    # Database
    PERSIST: bool = _get_bool.__func__("PERSIST", True)
    
    # Usage Limits
    DEFAULT_DAILY_LIMIT: int = _get_int.__func__("DEFAULT_DAILY_LIMIT", 25)
    GUEST_TOKEN_EXPIRE_MINUTES: int = _get_int.__func__("GUEST_TOKEN_EXPIRE_MINUTES", 60 * 24)
    GUEST_QUOTA_DEFAULT: int = _get_int.__func__("GUEST_QUOTA_DEFAULT", 5)
    
    # Conversation Settings
    CONVERSATION_HISTORY_DEPTH: int = _get_int.__func__("CONVERSATION_HISTORY_DEPTH", 10)
    
    # Plan Mode Settings
    PLAN_MAX_SCENES: int = _get_int.__func__("PLAN_MAX_SCENES", 10)
    PLAN_MAX_PARALLEL_WORKERS: int = _get_int.__func__("PLAN_MAX_PARALLEL_WORKERS", 3)
    PLAN_SCENE_TIMEOUT_SECONDS: int = _get_int.__func__("PLAN_SCENE_TIMEOUT_SECONDS", 300)
    
    # Pricing (USD per million tokens) - Update with actual Gemini pricing
    # These are placeholder values - adjust based on actual Gemini API pricing
    GEMINI_INPUT_PRICE_PER_MILLION: float = _get_float.__func__("GEMINI_INPUT_PRICE_PER_MILLION", 0.075)
    GEMINI_OUTPUT_PRICE_PER_MILLION: float = _get_float.__func__("GEMINI_OUTPUT_PRICE_PER_MILLION", 0.30)
    
    # Video pricing (per generation) - placeholder
    VIDEO_GENERATION_COST: float = _get_float.__func__("VIDEO_GENERATION_COST", 0.10)
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = _get_int.__func__("PORT", 8000)
    
    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY environment variable is required")
        if not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable is required")
    
    @classmethod
    def get_secret_key(cls) -> str:
        """Get SECRET_KEY, raise error if not set."""
        if not cls.SECRET_KEY:
            raise ValueError("SECRET_KEY must be set in environment variables")
        return cls.SECRET_KEY
    
    @classmethod
    def get_gemini_api_key(cls) -> str:
        """Get GEMINI_API_KEY, raise error if not set."""
        if not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY must be set in environment variables")
        return cls.GEMINI_API_KEY


# Initialize directories
try:
    os.makedirs(Config.ASSETS_DIR, exist_ok=True)
    os.makedirs(Config.VIDEOS_DIR, exist_ok=True)
    os.makedirs(Config.AVATARS_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning: Failed to create directories: {e}")
    print("Some features may not work correctly without these directories.")

