from typing import Annotated, Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_current_user_optional,
    get_db,
    require_space_role,
)
from app.models.space import Space, SpaceMember, SpaceRole
from app.models.user import SystemRole, User
from app.repositories.floor_repository import floor_repo
from app.repositories.space_repository import space_repo
from app.repositories.user_repository import user_repo
from app.schemas.floor import FloorCreate, FloorRead
from app.schemas.space import (
    SpaceCreate,
    SpaceMemberCreate,
    SpaceMemberRead,
    SpacePublishUpdate,
    SpaceRead,
    SpaceUpdate,
)

router = APIRouter(prefix="/spaces", tags=["Spaces & Floors"])


@router.get(
    "",
    response_model=List[SpaceRead],
    summary="Список доступных пространств текущего пользователя",
)
async def list_spaces(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> List[Space]:
    if current_user.system_role == SystemRole.SUPERADMIN:
        return await space_repo.list_all(db)
    return await space_repo.list_by_user(db, current_user.id)


@router.post(
    "",
    response_model=SpaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание нового пространства",
)
async def create_space(
    space_in: SpaceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Space:
    existing = await space_repo.get_by_slug(db, space_in.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Space with this slug already exists",
        )

    return await space_repo.create(db, space_in, owner_id=current_user.id)


@router.get(
    "/{space_id}",
    response_model=SpaceRead,
    summary="Карточка пространства со списком этажей",
)
async def get_space(
    space_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)],
) -> Space:
    space = await space_repo.get_by_id(db, space_id)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space not found",
        )

    # If space is published, any user or visitor can view it
    if space.is_published:
        return space

    # If not published, verify authentication and permissions
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to view unpublished space",
        )

    if current_user.system_role == SystemRole.SUPERADMIN:
        return space

    member = await space_repo.get_member(db, space_id, current_user.id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to unpublished space",
        )

    return space


@router.patch(
    "/{space_id}",
    response_model=SpaceRead,
    summary="Редактирование метаданных пространства (owner, editor)",
)
async def update_space(
    space_id: uuid.UUID,
    space_in: SpaceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[
        tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER, SpaceRole.EDITOR])),
    ],
) -> Space:
    space, _ = context

    if space_in.slug is not None and space_in.slug.lower() != space.slug:
        existing = await space_repo.get_by_slug(db, space_in.slug)
        if existing and existing.id != space.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Space with this slug already exists",
            )

    return await space_repo.update(db, space, space_in)


@router.patch(
    "/{space_id}/publish",
    response_model=SpaceRead,
    summary="Публикация / снятие с публикации (owner, editor)",
)
async def set_space_publish_status(
    space_id: uuid.UUID,
    publish_in: SpacePublishUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[
        tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER, SpaceRole.EDITOR])),
    ],
) -> Space:
    space, _ = context
    return await space_repo.set_publish_status(db, space, publish_in.is_published)


@router.delete(
    "/{space_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление пространства (owner, superadmin)",
)
async def delete_space(
    space_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    context: Annotated[
        tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER])),
    ],
) -> None:
    space, _ = context
    await space_repo.delete(db, space)
    await db.commit()


@router.post(
    "/{space_id}/members",
    response_model=SpaceMemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Добавление участника в команду пространства (owner)",
)
async def add_space_member(
    space_id: uuid.UUID,
    member_in: SpaceMemberCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER])),
    ],
) -> SpaceMemberRead:
    invited_user = await user_repo.get_by_email(db, member_in.email)
    if not invited_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User with this email not found",
        )

    member = await space_repo.add_or_update_member(
        db,
        space_id=space_id,
        user_id=invited_user.id,
        role=member_in.role,
    )

    return SpaceMemberRead(
        id=member.id,
        space_id=member.space_id,
        user_id=member.user_id,
        role=member.role,
        created_at=member.created_at,
        user_email=invited_user.email,
        user_full_name=invited_user.full_name,
    )


@router.post(
    "/{space_id}/floors",
    response_model=FloorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание этажа в пространстве (owner, editor)",
)
async def create_floor(
    space_id: uuid.UUID,
    floor_in: FloorCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[
        tuple[Space, Optional[SpaceMember]],
        Depends(require_space_role([SpaceRole.OWNER, SpaceRole.EDITOR])),
    ],
) -> FloorRead:
    existing_floor = await floor_repo.get_by_space_and_number(
        db, space_id, floor_in.floor_number
    )
    if existing_floor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Floor with number {floor_in.floor_number} already exists in this space",
        )

    floor = await floor_repo.create(db, space_id, floor_in)
    return FloorRead.model_validate(floor)
