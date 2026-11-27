"""Request/response schemas used across the API."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    """Validated payload for the optional local-development self-registration route."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("Enter a valid email address")
        return email


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    global_role: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    domain: str = Field(min_length=3, max_length=255)
    description: str = ""
    organization_id: int | None = None


class JobCreate(BaseModel):
    job_type: str
    name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    project_id: int | None = None


class ActionResponse(BaseModel):
    success: bool
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class IssueUpdate(BaseModel):
    status: str | None = None
    owner: str | None = None
    due_date: str | None = None
    resolution_notes: str | None = None
    validation_status: str | None = None
    priority: str | None = None
