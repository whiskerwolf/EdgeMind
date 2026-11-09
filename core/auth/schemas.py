"""
Pydantic Schemas for Authentication and User Profiles.
"""

import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRegister(BaseModel):
    """Schema for public user registration. Disallows arbitrary role specification."""
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=3, max_length=255, description="Unique user email address")
    password: str = Field(..., min_length=8, max_length=128, description="Plaintext password meeting complexity policy")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full human name of the user")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
            raise ValueError(f"Invalid email address format: '{v}'")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Full name must not be empty or whitespace-only.")
        return cleaned


class UserLogin(BaseModel):
    """Schema for user credentials authentication."""
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., description="Registered user email")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    """Response containing access and refresh tokens."""
    model_config = ConfigDict(extra="ignore")

    access_token: str = Field(..., description="Short-lived HS256 signed bearer access token")
    refresh_token: str = Field(..., description="Long-lived rotation-enabled refresh token")
    token_type: str = Field(default="bearer", description="Token authentication scheme")
    expires_in: int = Field(default=900, description="Access token expiration window in seconds")


class RefreshRequest(BaseModel):
    """Schema for rotating an existing refresh token."""
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(..., min_length=10, description="Valid signed refresh token")


class UserResponse(BaseModel):
    """Safe public user profile schema, omitting sensitive credential hashes."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique User UUID")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="User full display name")
    role: str = Field(..., description="Assigned authorization role (user or admin)")
    is_active: bool = Field(..., description="Account active status")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserUpdate(BaseModel):
    """Schema for self-service user profile updates. Privileges and roles are immutable."""
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    current_password: Optional[str] = Field(default=None, description="Required when changing password")
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Full name must not be whitespace-only.")
        return cleaned


class MessageResponse(BaseModel):
    """Simple status/confirmation response."""
    model_config = ConfigDict(extra="ignore")

    message: str

