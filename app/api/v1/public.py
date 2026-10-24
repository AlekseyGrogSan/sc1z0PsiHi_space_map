import uuid
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional, get_db
from app.models.poi import POI
from app.models.user import SystemRole, User
from app.repositories.poi_repository import poi_photo_repo, poi_repo
from app.repositories.space_repository import space_repo
from app.schemas.public import (
    PublicPOIPhotosResponse,
    PublicPOIPhotoRead,
    PublicSpaceBundleRead,
)

router = APIRouter(prefix="/public", tags=["Public Mobile Viewer"])


@router.get(
    "/spaces/{slug}",
    response_model=PublicSpaceBundleRead,
    summary="Публичный агрегированный пакет данных пространства для мобильного клиента",
)
async def get_public_space_bundle(
    slug: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Optional[User], Depends(get_current_user_optional)] = None,
) -> PublicSpaceBundleRead:
    space = await space_repo.get_public_bundle_by_slug(db, slug)
    if not space:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public space not found",
        )

    # Если пространство еще не опубликовано, разрешаем просмотр только создателю/участникам или суперадмину
    if not space.is_published:
        is_allowed = False
        if current_user:
            if current_user.system_role == SystemRole.SUPERADMIN:
                is_allowed = True
            else:
                member = await space_repo.get_member(db, space.id, current_user.id)
                if member:
                    is_allowed = True
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Public space not found or not published",
            )

    # Set aggressive caching header only for published spaces
    if space.is_published:
        response.headers["Cache-Control"] = "public, max-age=60"

    return PublicSpaceBundleRead.model_validate(space)


@router.get(
    "/pois/{poi_id}/photos",
    response_model=PublicPOIPhotosResponse,
    summary="Публичный список фотографий галереи POI",
)
async def get_public_poi_photos(
    poi_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Возвращает упорядоченный список ссылок на фотографии для данного POI.
    Не требует авторизации. Фотографии отдаются через presigned URL
    или публичный S3-префикс (CDN).
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    photos = await poi_photo_repo.list_by_poi(db, poi_id)
    return {
        "poi_id": poi_id,
        "poi_title": poi.title,
        "photos": photos,
    }