import os
import uuid
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.repositories.floor_repository import floor_repo
from app.schemas.floor import FloorRead, FloorUpdate
from app.schemas.media import (
    FloorPlanConfirmRequest,
    MediaProcessStatusResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.image_ops import image_service
from app.services.s3 import s3_service

router = APIRouter(prefix="/media", tags=["Media & Plans"])


@router.get(
    "/public/{file_path:path}",
    summary="Публичная отдача медиафайлов из бакета spaces-public (планы этажей, превью, тайлы)",
)
async def get_public_media_file(file_path: str):
    """
    Отдает файл из публичного S3 бакета напрямую через FastAPI,
    гарантируя доступность с любого IP/домена без необходимости открывать порт MinIO.
    """
    try:
        content_bytes = await s3_service.get_bytes(settings.S3_BUCKET_PUBLIC, file_path)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Медиафайл '{file_path}' не найден в хранилище",
        )

    ext = os.path.splitext(file_path)[1].lower()
    content_type_map = {
        ".webp": "image/webp",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
        ".json": "application/json",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")
    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _process_floor_plan_task(floor_id: uuid.UUID, staging_key: str):
    """Фоновая обработка плана этажа: конвертация из PNG/JPG/PDF в WebP, превью и замер размеров."""
    try:
        # Скачиваем сырой чертеж из staging
        raw_bytes = await s3_service.get_bytes(settings.S3_BUCKET_STAGING, staging_key)
        
        # Рендерим в растровый формат (если был PDF или картинка)
        raster_bytes, width, height = image_service.render_plan_to_bytes(raw_bytes, staging_key)
        
        # Генерируем оптимизированный WebP (до 2048px) и миниатюру
        optimized_webp = image_service.generate_optimized_floor_plan(raster_bytes)
        thumb_webp = image_service.generate_thumbnail_webp(raster_bytes)

        # Ключи для публичного бакета
        dest_opt_key = f"floors/{floor_id}/plan/optimized.webp"
        dest_thumb_key = f"floors/{floor_id}/plan/thumb.webp"

        await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_opt_key, optimized_webp, "image/webp")
        await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_thumb_key, thumb_webp, "image/webp")

        # Удаляем временный файл из staging
        await s3_service.delete_object(settings.S3_BUCKET_STAGING, staging_key)

        # Обновляем метаданные этажа в БД
        try:
            from app.core.database import async_session_factory
            async with async_session_factory() as db:
                floor = await floor_repo.get_by_id(db, floor_id)
                if floor:
                    await floor_repo.update(
                        db,
                        floor,
                        FloorUpdate(
                            plan_original_key=dest_opt_key,
                            plan_optimized_key=dest_opt_key,
                            width_px=width,
                            height_px=height,
                        ),
                    )
                    await db.commit()
        except Exception as db_err:
            print(f"Notice: floor record update skipped in background: {db_err}")
    except Exception as e:
        # Логируем ошибку фоновой обработки
        print(f"Error processing floor plan {floor_id}: {e}")

@router.post(
    "/floors/{floor_id}/plan/upload",
    response_model=FloorRead,
    summary="Загрузка готового файла плана этажа (PNG, JPG, WebP, PDF)",
)
async def upload_floor_plan(
    floor_id: uuid.UUID,
    file: UploadFile = File(..., description="Файл готового чертежа (PNG, JPG, WebP, PDF)"),
    ppm: Optional[float] = None,
    page_index: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Прямая загрузка готового плана этажа через Swagger UI или веб-форму.
    Поддерживает чертежи в растровых форматах (PNG, JPG, WebP), а также PDF-экспликации/чертежи БТИ.
    Автоматически оптимизирует чертеж в WebP, сохраняет в MinIO S3 и привязывает к этажу.
    """
    floor = await floor_repo.get_by_id(db, floor_id)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Этаж не найден")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Загруженный файл пустой")

    filename = file.filename or "plan.png"

    try:
        raster_bytes, width, height = image_service.render_plan_to_bytes(
            raw_bytes, filename=filename, page_index=page_index
        )
        optimized_webp = image_service.generate_optimized_floor_plan(raster_bytes)
        thumb_webp = image_service.generate_thumbnail_webp(raster_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не удалось обработать план: {str(e)}",
        )

    dest_opt_key = f"floors/{floor_id}/plan/optimized.webp"
    dest_thumb_key = f"floors/{floor_id}/plan/thumb.webp"

    await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_opt_key, optimized_webp, "image/webp")
    await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_thumb_key, thumb_webp, "image/webp")

    update_data = FloorUpdate(
        plan_original_key=dest_opt_key,
        plan_optimized_key=dest_opt_key,
        width_px=width,
        height_px=height,
    )
    if ppm is not None and ppm > 0:
        update_data.ppm = ppm

    updated_floor = await floor_repo.update(db, floor, update_data)
    await db.commit()
    return FloorRead.model_validate(updated_floor)

@router.post("/floors/{floor_id}/plan/upload-url", response_model=PresignedUploadResponse)
async def get_floor_plan_upload_url(
    floor_id: uuid.UUID,
    payload: PresignedUploadRequest,
):
    """
    Получение Presigned S3 PUT URL для прямой загрузки чертежа/плана этажа со смартфона или браузера.
    Файл загружается напрямую в MinIO без прогона через память FastAPI.
    """
    ext = os.path.splitext(payload.file_name)[1].lower() or ".png"
    storage_key = f"floors/{floor_id}/plan/raw_{uuid.uuid4().hex[:8]}{ext}"
    
    upload_url = await s3_service.generate_presigned_put_url(
        bucket=settings.S3_BUCKET_STAGING,
        key=storage_key,
        content_type=payload.content_type,
        expires_in=900,
    )

    return PresignedUploadResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in_seconds=900,
    )

@router.post("/floors/{floor_id}/plan/confirm-upload", response_model=MediaProcessStatusResponse)
async def confirm_floor_plan_upload(
    floor_id: uuid.UUID,
    payload: FloorPlanConfirmRequest,
    background_tasks: BackgroundTasks,
):
    """
    Подтверждение успешной загрузки чертежа в MinIO.
    Запускает фоновую конвертацию в WebP, нарезку миниатюр и сохранение в spaces-public.
    """
    background_tasks.add_task(_process_floor_plan_task, floor_id, payload.storage_key)
    return MediaProcessStatusResponse(
        status="processing",
        message="Floor plan upload confirmed. Processing started in background.",
    )

@router.post("/presigned-upload", response_model=PresignedUploadResponse)
async def get_general_presigned_upload_url(
    payload: PresignedUploadRequest,
    folder: str = "general",
):
    """Универсальный эндпоинт генерации Presigned URL для любых других медиафайлов (стенды, фото POI)."""
    ext = os.path.splitext(payload.file_name)[1].lower() or ".jpg"
    storage_key = f"{folder}/{uuid.uuid4().hex}{ext}"

    upload_url = await s3_service.generate_presigned_put_url(
        bucket=settings.S3_BUCKET_PUBLIC,
        key=storage_key,
        content_type=payload.content_type,
        expires_in=900,
    )

    return PresignedUploadResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in_seconds=900,
    )


@router.delete(
    "/floors/{floor_id}/plan",
    response_model=FloorRead,
    summary="Удаление чертежа/подложки этажа",
)
async def delete_floor_plan(
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    floor = await floor_repo.get_by_id(db, floor_id)
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Этаж не найден")

    if floor.plan_optimized_key:
        try:
            await s3_service.delete_object(settings.S3_BUCKET_PUBLIC, floor.plan_optimized_key)
        except Exception as e:
            print(f"Notice: S3 delete plan_optimized_key failed: {e}")

    if floor.plan_original_key and floor.plan_original_key != floor.plan_optimized_key:
        try:
            await s3_service.delete_object(settings.S3_BUCKET_PUBLIC, floor.plan_original_key)
        except Exception as e:
            print(f"Notice: S3 delete plan_original_key failed: {e}")

    floor.plan_original_key = None
    floor.plan_optimized_key = None
    floor.plan_tiles_prefix = None
    await db.commit()
    await db.refresh(floor)
    return FloorRead.model_validate(floor)
