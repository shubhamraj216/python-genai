"""
Modular FastAPI application for image generation with Gemini AI.

Features:
- User authentication (signup, login, guest)
- Image generation using Gemini API with persona-based system prompts
- Conversation management
- Asset metadata tracking
- Usage limits and quotas
"""
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import time
import json
from typing import Any, Dict, List, Union

from config import Config
from auth.routes import router as auth_router
from image.routes import router as image_router
from videos.routes import router as videos_router
from conversations.routes import router as conversations_router
from assets.routes import router as assets_router
from avatars.routes import router as avatars_router
from common.routes import router as unified_router
from utils.logger import get_logger
from common.error_messages import ErrorCode, get_error_response

# Initialize logger
logger = get_logger("main")

# Sensitive fields that should be masked in logs
SENSITIVE_FIELDS = {
    'access_token', 'token', 'password', 'reset_token', 
    'refresh_token', 'api_key', 'secret', 'authorization'
}


def mask_sensitive_data(data: Any, mask_value: str = "***MASKED***") -> Any:
    """
    Recursively mask sensitive fields in data structures.
    
    Args:
        data: Data to mask (dict, list, or string)
        mask_value: Value to replace sensitive data with
    
    Returns:
        Data with sensitive fields masked
    """
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            # Check if key is sensitive (case-insensitive)
            if key.lower() in SENSITIVE_FIELDS:
                masked[key] = mask_value
            else:
                masked[key] = mask_sensitive_data(value, mask_value)
        return masked
    elif isinstance(data, list):
        return [mask_sensitive_data(item, mask_value) for item in data]
    elif isinstance(data, str):
        # Try to parse as JSON and mask if successful
        try:
            parsed = json.loads(data)
            if isinstance(parsed, (dict, list)):
                return json.dumps(mask_sensitive_data(parsed, mask_value))
        except (json.JSONDecodeError, ValueError):
            pass
        return data
    else:
        return data

# Validate configuration on startup
try:
    Config.validate()
    logger.info("Configuration validated successfully")
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    logger.error("Please set required environment variables in .env file")
    print(f"Configuration error: {e}")
    print("Please set required environment variables in .env file")

# Create FastAPI app
app = FastAPI(
    title="Unified Multi-Modal Generation API",
    description="Unified API for text, image, and video generation with persona-based prompts, conversation history, and cost tracking. Built with type-safe Pydantic models.",
    version="3.2.0"
)


# CORS middleware - MUST be added FIRST so it runs on all responses (including error responses and OPTIONS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions globally."""
    # Don't catch HTTPException - let FastAPI handle those
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    # Log the unexpected error
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Return a user-friendly error
    message, status_code = get_error_response(ErrorCode.UNKNOWN_ERROR)
    return JSONResponse(
        status_code=status_code,
        content={"detail": message}
    )


# Request logging middleware - runs AFTER CORS middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing and request/response details."""
    start_time = time.time()
    
    try:
        # Build full URL with query params
        full_url = str(request.url)
        
        # Check if this is a static file request (skip response body logging for these)
        is_static_file = request.url.path.startswith("/assets/")
        
        # Capture request body
        request_body = None
        body_bytes = b""
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    request_body = body_bytes.decode('utf-8')
                    # Mask sensitive data before logging
                    masked_body = mask_sensitive_data(request_body)
                    # Truncate large bodies
                    if len(masked_body) > 2000:
                        masked_body = masked_body[:2000] + "... [truncated]"
                    request_body = masked_body
            except Exception as e:
                request_body = f"[Error reading body: {str(e)}]"
        
        # Log request with details
        log_msg = f"→ {request.method} {full_url} - Client: {request.client.host if request.client else 'unknown'}"
        if request_body:
            log_msg += f"\n  Request Body: {request_body}"
        logger.info(log_msg)
        
        # Process request (need to create a new request with the body we read)
        from fastapi import Request as FastAPIRequest
        
        async def receive():
            return {"type": "http.request", "body": body_bytes}
        
        if request.method in ["POST", "PUT", "PATCH"] and body_bytes:
            # Create new request with body available for re-reading
            request = FastAPIRequest(request.scope, receive)
        
        response = await call_next(request)
        
        # For static files (images, videos), don't try to read response body
        # This prevents breaking range requests and file streaming
        if is_static_file:
            process_time = (time.time() - start_time) * 1000
            logger.info(f"← {request.method} {full_url} - Status: {response.status_code} - Time: {process_time:.2f}ms")
            return response
        
        # Capture response body for API endpoints only
        response_body = None
        try:
            # Read response body
            response_body_bytes = b""
            async for chunk in response.body_iterator:
                response_body_bytes += chunk
            
            if response_body_bytes:
                response_body = response_body_bytes.decode('utf-8')
                # Mask sensitive data before logging
                masked_response = mask_sensitive_data(response_body)
                # Truncate large responses
                if len(masked_response) > 2000:
                    masked_response = masked_response[:2000] + "... [truncated]"
                response_body = masked_response
            
            # Create new response with the same body
            from fastapi import Response
            response = Response(
                content=response_body_bytes,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type
            )
        except Exception as e:
            response_body = f"[Error reading response: {str(e)}]"
        
        # Log response with timing and details
        process_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        log_msg = f"← {request.method} {full_url} - Status: {response.status_code} - Time: {process_time:.2f}ms"
        if response_body:
            log_msg += f"\n  Response Body: {response_body}"
        logger.info(log_msg)
        
        return response
    except Exception as e:
        # Log the error
        process_time = (time.time() - start_time) * 1000
        full_url = str(request.url) if hasattr(request, 'url') else 'unknown'
        logger.error(f"← {request.method} {full_url} - Error: {str(e)} - Time: {process_time:.2f}ms")
        
        # Re-raise to be handled by global exception handler
        raise

logger.info("CORS middleware configured")

# Serve static assets
try:
    app.mount("/assets", StaticFiles(directory="assets"), name="assets")
    logger.info("Static files mounted at /assets")
except Exception as e:
    logger.error(f"Failed to mount static files: {e}")
    logger.warning("Static file serving may not work correctly")

# Include routers
app.include_router(auth_router)
logger.info("Auth router included")

app.include_router(unified_router)
logger.info("Unified router included")

app.include_router(image_router)
logger.info("Image router included")

app.include_router(videos_router)
logger.info("Videos router included")

app.include_router(conversations_router)
logger.info("Conversations router included")

app.include_router(assets_router)
logger.info("Assets router included")

app.include_router(avatars_router)
logger.info("Avatars router included")


@app.on_event("startup")
async def startup_event():
    """Log startup event."""
    try:
        logger.info("=" * 80)
        logger.info("FastAPI application starting up")
        logger.info(f"Environment: {'Production' if Config.SECRET_KEY != 'dev-secret-key-change-in-prod' else 'Development'}")
        logger.info(f"Host: {Config.HOST}:{Config.PORT}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Error during startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event."""
    try:
        logger.info("=" * 80)
        logger.info("FastAPI application shutting down")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


@app.get("/healthz")
def health():
    """Health check endpoint."""
    try:
        logger.debug("Health check requested")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "message": "Service health check failed"}


# Run server directly
if __name__ == "__main__":
    logger.info(f"Starting server on {Config.HOST}:{Config.PORT}")
    uvicorn.run(
        "app:app", 
        host=Config.HOST, 
        port=Config.PORT, 
        reload=True,
        log_level="info"
    )
