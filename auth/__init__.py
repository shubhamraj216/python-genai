"""Authentication module."""
from auth.models import AuthSignupReq, AuthLoginReq
from auth.services import (
    get_user_by_email,
    get_user_by_id,
    create_user,
    update_user_fields,
    authenticate_user,
    get_current_user,
    create_access_token,
    decode_token
)

__all__ = [
    "AuthSignupReq",
    "AuthLoginReq",
    "get_user_by_email",
    "get_user_by_id",
    "create_user",
    "update_user_fields",
    "authenticate_user",
    "get_current_user",
    "create_access_token",
    "decode_token"
]

