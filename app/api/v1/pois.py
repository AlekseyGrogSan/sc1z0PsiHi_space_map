import os
import uuid
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.models.floor import Floor
from app.models.panorama import Panorama
from app.models.poi import POI, POIPhoto
from app.repositories.poi_repository import poi_photo_repo, poi_repo
from app.schemas.media import PresignedUploadRequest
from app.schemas.poi import (
    POICreate,
    POIRead,
    POIUpdate,
    POIPhotoConfirmRequest,
    POIPhotoDeleteResponse,
    POIPhotoListResponse,
    POIPhotoRead,
    POIPhotoReorderRequest,
    POIPhotoUploadResponse,
)
from app.services.s3 import s3_service

router = APIRouter(tags=["POI (Points of Interest)"])


async def _validate_panorama_binding(
    db: AsyncSession,
    panorama_id: uuid.UUID,
    floor_id: uuid.UUID,
) -> None:
    """
    Проверяет, что панорама существует и принадлежит тому же этажу, что и POI.
    """
    panorama = await db.get(Panorama, panorama_id)
    if not panorama:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Panorama not found",
        )
    if panorama.floor_id != floor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Panorama belongs to a different floor",
        )


@router.post(
    "/floors/{floor_id}/pois",
    response_model=POIRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создание точки интереса на этаже",
)
async def create_poi(
    floor_id: uuid.UUID,
    payload: POICreate,
    db: AsyncSession = Depends(get_db),
) -> POI:
    """
    Создает POI с обязательной привязкой к этажу и координатами (x, y) на 2D-плане.
    Опционально привязывает точку к существующей панораме этого же этажа
    (panorama_id + углы yaw_in_panorama/pitch_in_panorama).
    """
    floor = await db.get(Floor, floor_id)
    if not floor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Floor not found",
        )

    if payload.panorama_id is not None:
        await _validate_panorama_binding(db, payload.panorama_id, floor_id)

    return await poi_repo.create(db, floor_id, payload)


@router.get(
    "/floors/{floor_id}/pois",
    response_model=List[POIRead],
    summary="Список всех POI этажа",
)
async def list_floor_pois(
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> List[POI]:
    return await poi_repo.list_by_floor(db, floor_id)


@router.get(
    "/pois/{poi_id}",
    response_model=POIRead,
    summary="Карточка точки интереса",
)
async def get_poi(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> POI:
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )
    return poi


@router.patch(
    "/pois/{poi_id}",
    response_model=POIRead,
    summary="Редактирование POI и привязка/отвязка панорамы",
)
async def update_poi(
    poi_id: uuid.UUID,
    payload: POIUpdate,
    db: AsyncSession = Depends(get_db),
) -> POI:
    """
    Частичное обновление POI.

    - Привязка к панораме: передать panorama_id (+ опционально yaw/pitch).
    - Отвязка от панорамы: передать panorama_id=null, углы сбросятся автоматически.
    - Установка углов без привязанной панорамы запрещена.
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    fields = payload.model_dump(exclude_unset=True)

    if "panorama_id" in fields:
        if fields["panorama_id"] is None:
            # Отвязка от панорамы: углы маркера теряют смысл, сбрасываем их
            fields["yaw_in_panorama"] = None
            fields["pitch_in_panorama"] = None
        else:
            await _validate_panorama_binding(db, fields["panorama_id"], poi.floor_id)

    # Итоговое состояние после применения изменений должно остаться консистентным:
    # углы маркера допустимы только при наличии привязанной панорамы
    effective_panorama_id = fields.get("panorama_id", poi.panorama_id)
    effective_yaw = fields.get("yaw_in_panorama", poi.yaw_in_panorama)
    effective_pitch = fields.get("pitch_in_panorama", poi.pitch_in_panorama)
    if effective_panorama_id is None and (
        effective_yaw is not None or effective_pitch is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot set panorama angles: POI is not bound to a panorama",
        )

    return await poi_repo.update(db, poi, fields)


@router.delete(
    "/pois/{poi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удаление точки интереса",
)
async def delete_poi(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )
    await poi_repo.delete(db, poi)


# ============================================================================
# POI Photo Gallery Endpoints
# ============================================================================


@router.post(
    "/pois/{poi_id}/photos/upload-url",
    response_model=POIPhotoUploadResponse,
    summary="Получить Presigned URL для загрузки фотографии POI",
)
async def get_poi_photo_upload_url(
    poi_id: uuid.UUID,
    payload: PresignedUploadRequest,
    db: AsyncSession = Depends(get_db),
) -> POIPhotoUploadResponse:
    """
    Генерирует Presigned S3 PUT URL для прямой загрузки фотографии POI
    (минуя FastAPI — файл идёт напрямую в MinIO).
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    ext = os.path.splitext(payload.file_name)[1].lower() or ".jpg"
    storage_key = f"poi_photos/{poi_id}/{uuid.uuid4().hex}{ext}"

    upload_url = await s3_service.generate_presigned_put_url(
        bucket=settings.S3_BUCKET_PUBLIC,
        key=storage_key,
        content_type=payload.content_type,
        expires_in=900,
    )

    return POIPhotoUploadResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in_seconds=900,
    )


@router.post(
    "/pois/{poi_id}/photos/confirm-upload",
    response_model=POIPhotoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Подтвердить загрузку фотографии и добавить её в галерею POI",
)
async def confirm_poi_photo_upload(
    poi_id: uuid.UUID,
    payload: POIPhotoConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> POIPhoto:
    """
    Подтверждает, что фотография успешно загружена в MinIO по ранее
    полученному Presigned URL, и добавляет запись о ней в галерею POI.
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    return await poi_photo_repo.create(
        db=db,
        poi_id=poi_id,
        storage_key=payload.storage_key,
    )


@router.get(
    "/pois/{poi_id}/photos",
    response_model=POIPhotoListResponse,
    summary="Список фотографий галереи POI",
)
async def list_poi_photos(
    poi_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Возвращает упорядоченный список всех фотографий галереи POI."""
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    photos = await poi_photo_repo.list_by_poi(db, poi_id)
    return {"poi_id": poi_id, "photos": photos}


@router.delete(
    "/pois/{poi_id}/photos/{photo_id}",
    status_code=status.HTTP_200_OK,
    response_model=POIPhotoDeleteResponse,
    summary="Удалить фотографию из галереи POI",
)
async def delete_poi_photo(
    poi_id: uuid.UUID,
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Удаляет фотографию из галереи POI (запись в БД и файл в S3).
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    photo = await poi_photo_repo.get_by_id(db, photo_id)
    if not photo or photo.poi_id != poi_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found in this POI gallery",
        )

    # Удаляем файл из S3
    try:
        await s3_service.delete_object(settings.S3_BUCKET_PUBLIC, photo.storage_key)
    except Exception:
        # Не бросаем ошибку если файла уже нет в S3
        pass

    await poi_photo_repo.delete(db, photo)

    return {"success": True, "message": "Photo deleted successfully"}


@router.patch(
    "/pois/{poi_id}/photos/reorder",
    response_model=POIPhotoListResponse,
    summary="Изменить порядок фотографий в галерее POI",
)
async def reorder_poi_photos(
    poi_id: uuid.UUID,
    payload: POIPhotoReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Изменяет порядок фотографий. Передаётся список photo_ids
    в том порядке, в котором фотографии должны отображаться.
    """
    poi = await poi_repo.get_by_id(db, poi_id)
    if not poi:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="POI not found",
        )

    try:
        photos = await poi_photo_repo.reorder(db, poi_id, payload.photo_ids)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"poi_id": poi_id, "photos": photos}
