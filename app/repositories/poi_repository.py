from typing import Dict, List, Optional
import uuid
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.poi import POI, POIPhoto
from app.schemas.poi import POICreate


class POIRepository:
    async def create(
        self,
        db: AsyncSession,
        floor_id: uuid.UUID,
        poi_in: POICreate,
    ) -> POI:
        poi = POI(floor_id=floor_id, **poi_in.model_dump())
        db.add(poi)
        await db.flush()
        await db.refresh(poi)
        return poi

    async def get_by_id(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
    ) -> Optional[POI]:
        stmt = select(POI).where(POI.id == poi_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_floor(
        self,
        db: AsyncSession,
        floor_id: uuid.UUID,
    ) -> List[POI]:
        """Все POI этажа (используется также публичным агрегатором /public/spaces/{slug})."""
        stmt = (
            select(POI)
            .where(POI.floor_id == floor_id)
            .order_by(POI.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        db: AsyncSession,
        poi: POI,
        fields: Dict,
    ) -> POI:
        """Применяет уже провалидированный набор полей к POI."""
        for field, value in fields.items():
            setattr(poi, field, value)
        await db.flush()
        await db.refresh(poi)
        return poi

    async def delete(
        self,
        db: AsyncSession,
        poi: POI,
    ) -> None:
        await db.delete(poi)
        await db.flush()


poi_repo = POIRepository()


class POIPhotoRepository:
    """
    Репозиторий для управления фотографиями галереи POI.

    Все операции выполняются в контексте существующей сессии БД.
    Удаление S3-объектов должно выполняться вызывающим кодом.
    """

    async def create(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
        storage_key: str,
    ) -> POIPhoto:
        """
        Создаёт запись фотографии с автоматическим расчётом sort_order
        (новое фото добавляется в конец галереи).
        """
        # Текущий максимальный order среди фото этого POI
        stmt = select(POIPhoto).where(POIPhoto.poi_id == poi_id).order_by(POIPhoto.sort_order.desc()).limit(1)
        result = await db.execute(stmt)
        last_photo = result.scalar_one_or_none()
        next_order = (last_photo.sort_order + 1) if last_photo else 0

        photo = POIPhoto(
            poi_id=poi_id,
            storage_key=storage_key,
            sort_order=next_order,
        )
        db.add(photo)
        await db.flush()
        await db.refresh(photo)
        return photo

    async def list_by_poi(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
    ) -> List[POIPhoto]:
        """Все фотографии POI, отсортированные по sort_order."""
        stmt = (
            select(POIPhoto)
            .where(POIPhoto.poi_id == poi_id)
            .order_by(POIPhoto.sort_order.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(
        self,
        db: AsyncSession,
        photo_id: uuid.UUID,
    ) -> Optional[POIPhoto]:
        stmt = select(POIPhoto).where(POIPhoto.id == photo_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(
        self,
        db: AsyncSession,
        photo: POIPhoto,
    ) -> None:
        await db.delete(photo)
        await db.flush()

    async def reorder(
        self,
        db: AsyncSession,
        poi_id: uuid.UUID,
        ordered_ids: List[uuid.UUID],
    ) -> List[POIPhoto]:
        """
        Устанавливает sort_order для фотографий в соответствии с переданным
        списком photo_ids. Все ID должны принадлежать одному POI.
        """
        existing = await self.list_by_poi(db, poi_id)
        existing_map = {p.id: p for p in existing}

        if set(ordered_ids) != set(existing_map.keys()):
            raise ValueError("photo_ids must match exactly the set of existing photos for this POI")

        for idx, photo_id in enumerate(ordered_ids):
            existing_map[photo_id].sort_order = idx

        await db.flush()

        # Возвращаем обновлённый список
        return await self.list_by_poi(db, poi_id)


poi_photo_repo = POIPhotoRepository()
