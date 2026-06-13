"""Auth / user schemas."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("username may contain only letters, numbers, _ and -")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email address")
        return v.lower()

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:
            raise ValueError("password must be <= 72 bytes")
        if not _PASSWORD_RE.match(v):
            raise ValueError("password must contain at least one letter and one number")
        return v


class UserLogin(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
