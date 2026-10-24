from typing import Dict, List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.poi import POI
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
