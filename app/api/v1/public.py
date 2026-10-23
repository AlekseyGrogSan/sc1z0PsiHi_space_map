from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.repositories.space_repository import space_repo
from app.schemas.public import PublicSpaceBundleRead

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
) -> PublicSpaceBundleRead:
    space = await space_repo.get_by_slug(db, slug)
    if not space or not space.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Public space not found or not published",
        )

    # Set aggressive caching header for mobile clients / CDN
    response.headers["Cache-Control"] = "public, max-age=60"

    return PublicSpaceBundleRead.model_validate(space)
