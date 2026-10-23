from typing import Annotated, List
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_superadmin
from app.models.user import User
from app.repositories.user_repository import user_repo
from app.schemas.user import UserRead, UserStatusUpdate

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/users",
    response_model=List[UserRead],
    summary="Список всех пользователей системы (только superadmin)",
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_superadmin)],
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> List[User]:
    return await user_repo.list_users(db, skip=skip, limit=limit)


@router.patch(
    "/users/{user_id}/status",
    response_model=UserRead,
    summary="Блокировка / разблокировка учетной записи (только superadmin)",
)
async def update_user_status(
    user_id: uuid.UUID,
    status_in: UserStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_admin: Annotated[User, Depends(require_superadmin)],
) -> User:
    if user_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change status of your own administrator account",
        )

    user = await user_repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return await user_repo.update_status(db, user, status_in.is_active)
