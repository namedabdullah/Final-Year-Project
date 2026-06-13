"""Auth routes: signup, login, me, logout. SAMpai app users (not the server's
env-account auth)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from lightrag.api.sampai.constants import RESERVED_USERNAMES
from lightrag.api.sampai.db import get_db
from lightrag.api.sampai.deps import get_current_user
from lightrag.api.sampai.models.user import User
from lightrag.api.sampai.schemas.user import (
    TokenResponse,
    UserCreate,
    UserLogin,
    UserOut,
)
from lightrag.api.sampai.security import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["sampai-auth"])
logger = logging.getLogger("sampai.auth")


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if payload.username.lower() in RESERVED_USERNAMES:
        raise HTTPException(status_code=422, detail="This username is reserved")

    existing = await db.scalar(
        select(User).where(
            or_(User.email == payload.email, User.username == payload.username)
        )
    )
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email or username already registered")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Email or username already registered")

    logger.info("signup ok user_id=%s username=%s", user.id, user.username)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    settings = request.app.state.sampai_settings
    token = create_access_token(
        user_id=user.id,
        secret=settings.app_jwt_secret,
        expire_minutes=settings.app_jwt_expire_min,
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout():
    # Stateless JWT — client discards the token. Endpoint exists for symmetry.
    return {"message": "Logout successful"}
