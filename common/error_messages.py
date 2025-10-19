"""
User-friendly error messages and status codes.

This module provides centralized error message definitions that are
user-friendly and avoid exposing technical implementation details.
"""
from typing import Tuple, Optional
from enum import Enum


class ErrorCode(str, Enum):
    """Error codes for different types of failures."""
    
    # Authentication Errors (401, 403)
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    EMAIL_IN_USE = "EMAIL_IN_USE"
    
    # Validation Errors (400)
    MISSING_FIELD = "MISSING_FIELD"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_IMAGE_DATA = "INVALID_IMAGE_DATA"
    INVALID_VIDEO_DATA = "INVALID_VIDEO_DATA"
    
    # Not Found Errors (404)
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    PERSONA_NOT_FOUND = "PERSONA_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    
    # Rate Limit Errors (429, 403)
    DAILY_LIMIT_REACHED = "DAILY_LIMIT_REACHED"
    GUEST_QUOTA_EXHAUSTED = "GUEST_QUOTA_EXHAUSTED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # External API Errors (502, 503)
    GEMINI_API_ERROR = "GEMINI_API_ERROR"
    GEMINI_TIMEOUT = "GEMINI_TIMEOUT"
    GEMINI_RATE_LIMIT = "GEMINI_RATE_LIMIT"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    
    # File/Storage Errors (500)
    FILE_SAVE_ERROR = "FILE_SAVE_ERROR"
    FILE_READ_ERROR = "FILE_READ_ERROR"
    DISK_SPACE_ERROR = "DISK_SPACE_ERROR"
    
    # Database Errors (500)
    DATABASE_ERROR = "DATABASE_ERROR"
    DATA_CORRUPTION = "DATA_CORRUPTION"
    
    # Generation Errors (500, 502)
    GENERATION_FAILED = "GENERATION_FAILED"
    NO_CONTENT_GENERATED = "NO_CONTENT_GENERATED"
    VIDEO_GENERATION_FAILED = "VIDEO_GENERATION_FAILED"
    IMAGE_GENERATION_FAILED = "IMAGE_GENERATION_FAILED"
    
    # Configuration Errors (500)
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    MISSING_API_KEY = "MISSING_API_KEY"
    
    # Generic Errors
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"


# User-friendly error messages mapped to error codes
ERROR_MESSAGES = {
    # Authentication Errors
    ErrorCode.INVALID_CREDENTIALS: "The email or password you entered is incorrect. Please try again.",
    ErrorCode.TOKEN_EXPIRED: "Your session has expired. Please log in again to continue.",
    ErrorCode.INVALID_TOKEN: "Your session is invalid. Please log in again.",
    ErrorCode.USER_NOT_FOUND: "We couldn't find your account. Please check your credentials and try again.",
    ErrorCode.INSUFFICIENT_PERMISSIONS: "You don't have permission to perform this action.",
    ErrorCode.EMAIL_IN_USE: "This email address is already registered. Please use a different email or log in.",
    
    # Validation Errors
    ErrorCode.MISSING_FIELD: "Required information is missing. Please check your input and try again.",
    ErrorCode.INVALID_FORMAT: "The format of your input is incorrect. Please check and try again.",
    ErrorCode.INVALID_PARAMETER: "One or more parameters are invalid. Please review your request and try again.",
    ErrorCode.INVALID_IMAGE_DATA: "The image data provided is invalid or corrupted. Please try with a different image.",
    ErrorCode.INVALID_VIDEO_DATA: "The video data provided is invalid or corrupted. Please try with a different video.",
    
    # Not Found Errors
    ErrorCode.CONVERSATION_NOT_FOUND: "We couldn't find the conversation you're looking for. It may have been deleted.",
    ErrorCode.ASSET_NOT_FOUND: "The asset you're looking for is no longer available.",
    ErrorCode.PERSONA_NOT_FOUND: "The persona you're trying to use doesn't exist.",
    ErrorCode.RESOURCE_NOT_FOUND: "The requested resource could not be found.",
    
    # Rate Limit Errors
    ErrorCode.DAILY_LIMIT_REACHED: "You've reached your daily usage limit. Please try again tomorrow or upgrade your account.",
    ErrorCode.GUEST_QUOTA_EXHAUSTED: "Your guest quota has been used up. Please create an account to continue.",
    ErrorCode.RATE_LIMIT_EXCEEDED: "You're making requests too quickly. Please slow down and try again in a moment.",
    
    # External API Errors
    ErrorCode.GEMINI_API_ERROR: "We're having trouble connecting to our AI service. Please try again in a few moments.",
    ErrorCode.GEMINI_TIMEOUT: "The AI service is taking too long to respond. Please try again with a simpler request.",
    ErrorCode.GEMINI_RATE_LIMIT: "Our AI service is currently experiencing high demand. Please try again in a few minutes.",
    ErrorCode.EXTERNAL_SERVICE_ERROR: "An external service is temporarily unavailable. Please try again later.",
    
    # File/Storage Errors
    ErrorCode.FILE_SAVE_ERROR: "We couldn't save the file. Please try again.",
    ErrorCode.FILE_READ_ERROR: "We couldn't read the requested file. It may be corrupted or unavailable.",
    ErrorCode.DISK_SPACE_ERROR: "We're running low on storage space. Please contact support.",
    
    # Database Errors
    ErrorCode.DATABASE_ERROR: "We encountered a problem accessing your data. Please try again.",
    ErrorCode.DATA_CORRUPTION: "Some data appears to be corrupted. Please contact support if this persists.",
    
    # Generation Errors
    ErrorCode.GENERATION_FAILED: "We couldn't complete the generation. Please try again with a different prompt.",
    ErrorCode.NO_CONTENT_GENERATED: "No content was generated. Please try rephrasing your request.",
    ErrorCode.VIDEO_GENERATION_FAILED: "Video generation failed. Please try again or adjust your parameters.",
    ErrorCode.IMAGE_GENERATION_FAILED: "Image generation failed. Please try again or adjust your prompt.",
    
    # Configuration Errors
    ErrorCode.CONFIGURATION_ERROR: "There's a configuration problem with the service. Please contact support.",
    ErrorCode.MISSING_API_KEY: "The service is not properly configured. Please contact support.",
    
    # Generic Errors
    ErrorCode.UNKNOWN_ERROR: "Something unexpected happened. Please try again.",
    ErrorCode.OPERATION_FAILED: "The operation could not be completed. Please try again.",
}


# HTTP status codes for each error type
ERROR_STATUS_CODES = {
    # Authentication Errors
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.INVALID_TOKEN: 401,
    ErrorCode.USER_NOT_FOUND: 404,
    ErrorCode.INSUFFICIENT_PERMISSIONS: 403,
    ErrorCode.EMAIL_IN_USE: 400,
    
    # Validation Errors
    ErrorCode.MISSING_FIELD: 400,
    ErrorCode.INVALID_FORMAT: 400,
    ErrorCode.INVALID_PARAMETER: 400,
    ErrorCode.INVALID_IMAGE_DATA: 400,
    ErrorCode.INVALID_VIDEO_DATA: 400,
    
    # Not Found Errors
    ErrorCode.CONVERSATION_NOT_FOUND: 404,
    ErrorCode.ASSET_NOT_FOUND: 404,
    ErrorCode.PERSONA_NOT_FOUND: 404,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    
    # Rate Limit Errors
    ErrorCode.DAILY_LIMIT_REACHED: 429,
    ErrorCode.GUEST_QUOTA_EXHAUSTED: 403,
    ErrorCode.RATE_LIMIT_EXCEEDED: 429,
    
    # External API Errors
    ErrorCode.GEMINI_API_ERROR: 502,
    ErrorCode.GEMINI_TIMEOUT: 504,
    ErrorCode.GEMINI_RATE_LIMIT: 503,
    ErrorCode.EXTERNAL_SERVICE_ERROR: 502,
    
    # File/Storage Errors
    ErrorCode.FILE_SAVE_ERROR: 500,
    ErrorCode.FILE_READ_ERROR: 500,
    ErrorCode.DISK_SPACE_ERROR: 507,
    
    # Database Errors
    ErrorCode.DATABASE_ERROR: 500,
    ErrorCode.DATA_CORRUPTION: 500,
    
    # Generation Errors
    ErrorCode.GENERATION_FAILED: 500,
    ErrorCode.NO_CONTENT_GENERATED: 500,
    ErrorCode.VIDEO_GENERATION_FAILED: 500,
    ErrorCode.IMAGE_GENERATION_FAILED: 500,
    
    # Configuration Errors
    ErrorCode.CONFIGURATION_ERROR: 500,
    ErrorCode.MISSING_API_KEY: 500,
    
    # Generic Errors
    ErrorCode.UNKNOWN_ERROR: 500,
    ErrorCode.OPERATION_FAILED: 500,
}


def get_error_response(
    error_code: ErrorCode, 
    custom_message: Optional[str] = None,
    log_details: Optional[str] = None
) -> Tuple[str, int]:
    """
    Get user-friendly error message and HTTP status code.
    
    Args:
        error_code: The error code enum
        custom_message: Optional custom message to append to the standard message
        log_details: Optional technical details to log (not shown to user)
    
    Returns:
        Tuple of (error_message, status_code)
    """
    message = ERROR_MESSAGES.get(error_code, ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR])
    status_code = ERROR_STATUS_CODES.get(error_code, 500)
    
    if custom_message:
        message = f"{message} {custom_message}"
    
    return message, status_code


def format_error_detail(error_code: ErrorCode, detail: Optional[str] = None) -> str:
    """
    Format error detail for API response.
    
    Args:
        error_code: The error code enum
        detail: Optional additional detail
    
    Returns:
        Formatted error message
    """
    base_message = ERROR_MESSAGES.get(error_code, ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR])
    
    if detail:
        return f"{base_message} ({detail})"
    
    return base_message

