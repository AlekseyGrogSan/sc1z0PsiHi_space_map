import asyncio
import os
import uuid
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import async_session_factory, get_db
from app.models.panorama import Panorama, PanoramaHotspot, UploadSession
from app.schemas.media import (
    MediaProcessStatusResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.schemas.panorama import (
    PanoramaCreate,
    PanoramaHotspotCreate,
    PanoramaHotspotResponse,
    PanoramaPublicResponse,
    PanoramaResponse,
    PanoramaStatusResponse,
    PanoramaUpdate,
    StitchFrameUrl,
    StitchSessionCreate,
    StitchSessionResponse,
)
from app.services.image_ops import image_service
from app.services.s3 import s3_service

router = APIRouter(tags=["Panoramas & 3D Tour"])

# ============================================================================
# Фоновые воркеры обработки панорам (Background Tasks)
# ============================================================================

async def _process_ready_panorama_task(panorama_id: uuid.UUID, staging_key: str):
    """
    Фоновый пайплайн обработки готовой 360-панорамы:
    1. Скачивание из staging
    2. Расчет BlurHash
    3. Создание превью WebP (1024x512, ~50 КБ) для быстрой мобильной загрузки
    4. Нарезка Cubemap тайлов (6 граней) под Marzipano / Pannellum
    5. Загрузка в spaces-public и перевод статуса в 'ready'
    """
    async with async_session_factory() as session:
        try:
            # 1. Скачивание
            raw_bytes = await s3_service.get_bytes(settings.S3_BUCKET_STAGING, staging_key)

            # 2. Вычисления в пуле потоков
            def _compute_derivatives():
                bhash = image_service.compute_blurhash(raw_bytes)
                prev = image_service.generate_preview_webp(raw_bytes)
                cubemap = image_service.slice_equirectangular_to_cubemap(raw_bytes, face_size=512)
                return bhash, prev, cubemap

            bhash, preview_webp, cubemap_faces = await asyncio.to_thread(_compute_derivatives)

            # 3. Сохранение артефактов в spaces-public
            preview_key = f"panoramas/{panorama_id}/preview.webp"
            original_key = f"panoramas/{panorama_id}/original.webp"
            cubemap_prefix = f"panoramas/{panorama_id}/cubemap"

            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, original_key, raw_bytes, "image/jpeg")
            await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, preview_key, preview_webp, "image/webp")

            for face, face_bytes in cubemap_faces.items():
                face_key = f"{cubemap_prefix}/l1/{face}_0_0.webp"
                await s3_service.put_bytes(settings.S3_BUCKET_PUBLIC, face_key, face_bytes, "image/webp")

            # 4. Обновление записи в БД
            pano = await session.get(Panorama, panorama_id)
            if pano:
                pano.status = "ready"
                pano.blurhash = bhash
                pano.preview_key = preview_key
                pano.original_key = original_key
                pano.cubemap_prefix = cubemap_prefix
                pano.error_message = None
                await session.commit()

            # 5. Очистка staging
            await s3_service.delete_object(settings.S3_BUCKET_STAGING, staging_key)

        except Exception as e:
            pano = await session.get(Panorama, panorama_id)
            if pano:
                pano.status = "failed"
                pano.error_message = str(e)
                await session.commit()

async def _process_stitch_session_task(panorama_id: uuid.UUID, session_id: uuid.UUID, frame_count: int):
    """
    Фоновый воркер сшивки серии фото со смартфона через OpenCV Stitcher:
    """
    async with async_session_factory() as session:
        try:
            frames_bytes = []
            for i in range(frame_count):
                key = f"sessions/{session_id}/frame_{i}.jpg"
                frame_data = await s3_service.get_bytes(settings.S3_BUCKET_STAGING, key)
                frames_bytes.append(frame_data)

            # Сшивка в пуле потоков
            success, stitched_bytes, msg = await asyncio.to_thread(
                image_service.stitch_frames_opencv, frames_bytes
            )

            pano = await session.get(Panorama, panorama_id)
            sess = await session.get(UploadSession, session_id)

            if not success or stitched_bytes is None:
                if pano:
                    pano.status = "failed"
                    pano.error_message = f"Stitching failed: {msg}"
                if sess:
                    sess.status = "failed"
                await session.commit()
                return

            if sess:
                sess.status = "completed"
                await session.commit()

            # Сохраняем сшитый результат как исходник в staging и запускаем финальную обработку
            stitched_key = f"panoramas/{panorama_id}/stitched_raw.webp"
            await s3_service.put_bytes(settings.S3_BUCKET_STAGING, stitched_key, stitched_bytes, "image/webp")
            await _process_ready_panorama_task(panorama_id, stitched_key)

        except Exception as e:
            pano = await session.get(Panorama, panorama_id)
            if pano:
                pano.status = "failed"
                pano.error_message = f"Stitch pipeline error: {str(e)}"
                await session.commit()

# ============================================================================
# API Эндпоинты панорам
# ============================================================================

@router.post("/floors/{floor_id}/panoramas", response_model=PanoramaResponse, status_code=status.HTTP_201_CREATED)
async def create_panorama(
    floor_id: uuid.UUID,
    payload: PanoramaCreate,
    db: AsyncSession = Depends(get_db),
):
    """Создает точку панорамы с привязкой к координатам (x, y) на 2D-плане этажа."""
    panorama = Panorama(
        floor_id=floor_id,
        title=payload.title,
        x_coord=payload.x_coord,
        y_coord=payload.y_coord,
        initial_heading=payload.initial_heading,
        status="pending_upload",
    )
    db.add(panorama)
    await db.commit()
    await db.refresh(panorama)
    return panorama

@router.get("/floors/{floor_id}/panoramas", response_model=List[PanoramaResponse])
async def list_floor_panoramas(
    floor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Возвращает список всех панорам конкретного этажа со связями (Hotspots)."""
    stmt = (
        select(Panorama)
        .where(Panorama.floor_id == floor_id)
        .options(selectinload(Panorama.hotspots))
    )
    result = await db.execute(stmt)
    return result.scalars().all()

@router.get("/panoramas/{id}", response_model=PanoramaResponse)
async def get_panorama(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Получение детальной информации о панораме по ID."""
    stmt = select(Panorama).where(Panorama.id == id).options(selectinload(Panorama.hotspots))
    result = await db.execute(stmt)
    pano = result.scalar_one_or_none()
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")
    return pano

@router.patch("/panoramas/{id}", response_model=PanoramaResponse)
async def update_panorama(
    id: uuid.UUID,
    payload: PanoramaUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Обновление метаданных панорамы (название, координаты, азимут)."""
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    for field, val in payload.model_dump(exclude_unset=True).items():
        setattr(pano, field, val)

    await db.commit()
    await db.refresh(pano)
    return pano

@router.delete("/panoramas/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panorama(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Удаление панорамы и её артефактов."""
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    # Удаляем файлы из S3
    if pano.original_key:
        await s3_service.delete_object(settings.S3_BUCKET_PUBLIC, pano.original_key)
    if pano.preview_key:
        await s3_service.delete_object(settings.S3_BUCKET_PUBLIC, pano.preview_key)

    await db.delete(pano)
    await db.commit()

# ============================================================================
# Загрузка и запуск обработки готовой 360-панорамы
# ============================================================================

@router.post("/panoramas/{id}/upload-ready-url", response_model=PresignedUploadResponse)
async def get_panorama_upload_url(
    id: uuid.UUID,
    payload: PresignedUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Генерирует Presigned S3 PUT URL для готовой 360° фотографии.
    Клиент загружает исходный файл прямо в MinIO без нагрузки на FastAPI.
    """
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    ext = os.path.splitext(payload.file_name)[1].lower() or ".jpg"
    storage_key = f"panoramas/{id}/raw{ext}"

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

@router.post("/panoramas/{id}/confirm-upload", response_model=MediaProcessStatusResponse)
async def confirm_panorama_upload(
    id: uuid.UUID,
    background_tasks: BackgroundTasks,
    storage_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Подтверждение загрузки готовой 360-панорамы.
    Запускает расчет BlurHash, генерацию WebP-превью и нарезку Cubemap тайлов в фоне.
    """
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    key = storage_key or f"panoramas/{id}/raw.jpg"
    pano.status = "processing"
    await db.commit()

    background_tasks.add_task(_process_ready_panorama_task, id, key)
    return MediaProcessStatusResponse(
        status="processing",
        message="Panorama processing initiated in background.",
    )

@router.get("/panoramas/{id}/status", response_model=PanoramaStatusResponse)
async def get_panorama_status(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Опрос статуса готовности панорамы (pending_upload, processing, ready, failed)."""
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    preview_url = f"{settings.S3_PUBLIC_URL_PREFIX}/{pano.preview_key}" if pano.preview_key else None
    return PanoramaStatusResponse(
        id=pano.id,
        status=pano.status,
        blurhash=pano.blurhash,
        preview_url=preview_url,
        error_message=pano.error_message,
    )

# ============================================================================
# Сшивка серии фото со смартфона (Stitching Session)
# ============================================================================

@router.post("/panoramas/{id}/stitch-session", response_model=StitchSessionResponse)
async def create_stitch_session(
    id: uuid.UUID,
    payload: StitchSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Инициализирует сессию съемки серии кадров со смартфона (поворот на месте).
    Возвращает список Presigned PUT URLs для каждого кадра круговой серии.
    """
    pano = await db.get(Panorama, id)
    if not pano:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not found")

    session = UploadSession(
        panorama_id=id,
        frame_count=payload.frame_count,
        status="pending",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    frames = []
    for i in range(payload.frame_count):
        frame_key = f"sessions/{session.id}/frame_{i}.jpg"
        url = await s3_service.generate_presigned_put_url(
            bucket=settings.S3_BUCKET_STAGING,
            key=frame_key,
            content_type="image/jpeg",
            expires_in=1800,
        )
        frames.append(StitchFrameUrl(frame_index=i, upload_url=url, storage_key=frame_key))

    return StitchSessionResponse(
        session_id=session.id,
        panorama_id=id,
        frames=frames,
    )

@router.post("/panoramas/{id}/process-stitch", response_model=MediaProcessStatusResponse)
async def start_stitching(
    id: uuid.UUID,
    session_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Запускает алгоритм сшивки кадров серии через OpenCV в фоне."""
    pano = await db.get(Panorama, id)
    sess = await db.get(UploadSession, session_id)
    if not pano or not sess:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session or Panorama not found")

    pano.status = "processing"
    sess.status = "stitching"
    await db.commit()

    background_tasks.add_task(_process_stitch_session_task, id, session_id, sess.frame_count)
    return MediaProcessStatusResponse(
        status="processing",
        message="Stitching pipeline started.",
    )

# ============================================================================
# Связи панорам (Hotspots / Переходы)
# ============================================================================

@router.post("/panoramas/connections", response_model=PanoramaHotspotResponse, status_code=status.HTTP_201_CREATED)
async def create_panorama_connection(
    payload: PanoramaHotspotCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Создает стрелку-переход между панорамой A и панорамой B с углами yaw (-180..180) и pitch (-90..90).
    """
    source = await db.get(Panorama, payload.source_panorama_id)
    target = await db.get(Panorama, payload.target_panorama_id)
    if not source or not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source or Target panorama not found")

    hotspot = PanoramaHotspot(
        source_panorama_id=payload.source_panorama_id,
        target_panorama_id=payload.target_panorama_id,
        yaw=payload.yaw,
        pitch=payload.pitch,
        title=payload.title,
    )
    db.add(hotspot)
    await db.commit()
    await db.refresh(hotspot)
    return hotspot

@router.delete("/panoramas/connections/{hotspot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_panorama_connection(
    hotspot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Удаляет стрелку-переход между панорамами."""
    hotspot = await db.get(PanoramaHotspot, hotspot_id)
    if not hotspot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await db.delete(hotspot)
    await db.commit()

# ============================================================================
# Публичный эндпоинт для мобильного 3D-плеера (Pannellum / Marzipano)
# ============================================================================

@router.get("/public/panoramas/{id}", response_model=PanoramaPublicResponse)
async def get_public_panorama(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Легковесный эндпоинт для смартфона посетителя:
    Мгновенно отдает BlurHash, WebP-превью и шаблон кубических тайлов без авторизации.
    """
    stmt = select(Panorama).where(Panorama.id == id).options(selectinload(Panorama.hotspots))
    result = await db.execute(stmt)
    pano = result.scalar_one_or_none()
    if not pano or pano.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Panorama not ready or not found"
        )
    return pano
