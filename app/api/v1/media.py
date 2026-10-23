import os
import uuid
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.schemas.media import (
    FloorPlanConfirmRequest,
    MediaProcessStatusResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.image_ops import image_service
from app.services.s3 import s3_service

router = APIRouter(prefix="/media", tags=["Media & Plans"])

async def _process_floor_plan_task(floor_id: uuid.UUID, staging_key: str):
    """Фоновая обработка плана этажа: конвертация в WebP, превью и замер размеров."""
    try:
        # Скачиваем сырой чертеж из staging
        raw_bytes = await s3_service.get_bytes(settings.S3_BUCKET_STAGING, staging_key)
        
        # Получаем пропорции
        width, height = image_service.inspect_dimensions(raw_bytes)
        
        # Генерируем оптимизированный WebP (до 2048px) и миниатюру
        optimized_webp = image_service.generate_optimized_floor_plan(raw_bytes)
        thumb_webp = image_service.generate_thumbnail_webp(raw_bytes)

        # Ключи для публичного бакета
        dest_opt_key = f"floors/{floor_id}/plan/optimized.webp"
        dest_thumb_key = f"floors/{floor_id}/plan/thumb.webp"

        await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_opt_key, optimized_webp, "image/webp")
        await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, dest_thumb_key, thumb_webp, "image/webp")

        # Удаляем временный файл из staging
        await s3_service.delete_object(settings.S3_BUCKET_STAGING, staging_key)
    except Exception as e:
        # Логируем ошибку фоновой обработки
        print(f"Error processing floor plan {floor_id}: {e}")

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
