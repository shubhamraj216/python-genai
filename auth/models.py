"""Authentication Pydantic models."""
from typing import Optional
from pydantic import BaseModel


class AuthSignupReq(BaseModel):
    email: str
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class AuthLoginReq(BaseModel):
    email: str
    password: str

