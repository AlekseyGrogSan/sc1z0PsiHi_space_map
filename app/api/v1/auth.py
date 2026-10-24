from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import (
    check_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import SystemRole, User
from app.repositories.user_repository import user_repo
from app.schemas.user import (
    TokenRefreshRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserProfileRead,
    UserRead,
    UserSpaceMembershipRead,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация нового организатора",
)
async def register(
    user_in: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    existing_user = await user_repo.get_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )

    # First registered user can become superadmin if no users exist, otherwise organizer
    users = await user_repo.list_users(db, limit=1)
    system_role = SystemRole.SUPERADMIN if len(users) == 0 else SystemRole.ORGANIZER

    user = await user_repo.create(db, user_in, system_role=system_role)
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Получение пары JWT токенов (OAuth2 Password Flow)",
)
async def login(
    login_in: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    user = await user_repo.get_by_email(db, login_in.username)
    if not user or not await check_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Обновление пары токенов по Refresh токену",
)
async def refresh_token(
    refresh_in: TokenRefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        payload = decode_token(refresh_in.refresh_token)
        user_id_str = payload.get("sub")
        token_type = payload.get("type")
        if not user_id_str or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        user_id = uuid.UUID(user_id_str)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user = await user_repo.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get(
    "/me",
    response_model=UserProfileRead,
    summary="Профиль текущего пользователя и доступные пространства",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileRead:
    memberships = await user_repo.get_user_spaces(db, current_user.id)

    accessible_spaces = [
        UserSpaceMembershipRead(
            space_id=m.space_id,
            space_title=m.space.title,
            space_slug=m.space.slug,
            role=m.role,
        )
        for m in memberships
        if m.space is not None
    ]

    return UserProfileRead(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        system_role=current_user.system_role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        accessible_spaces=accessible_spaces,
    )
