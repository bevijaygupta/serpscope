"""Request/response schemas used across the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


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
