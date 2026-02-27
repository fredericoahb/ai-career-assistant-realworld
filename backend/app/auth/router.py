"""Auth + User profile endpoints – RealWorld Conduit-inspired schema."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.service import create_access_token, hash_password, verify_password, TokenData
from app.models.database import get_db
from app.models.db import User

router = APIRouter(prefix="/api/users", tags=["auth"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    username: str
    email: str
    bio: str | None
    image: str | None
    is_admin: bool
    token: str | None = None

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    bio: str | None = None
    image: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    exists = await db.execute(
        select(User).where((User.email == payload.email) | (User.username == payload.username))
    )
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Username or email already taken")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(TokenData(sub=user.username, is_admin=user.is_admin))
    return UserOut.model_validate(user).model_copy(update={"token": token})


@router.post("/login", response_model=UserOut)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user: User | None = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(TokenData(sub=user.username, is_admin=user.is_admin))
    return UserOut.model_validate(user).model_copy(update={"token": token})


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.put("/me", response_model=UserOut)
async def update_profile(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.bio is not None:
        current_user.bio = payload.bio
    if payload.image is not None:
        current_user.image = payload.image
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)
