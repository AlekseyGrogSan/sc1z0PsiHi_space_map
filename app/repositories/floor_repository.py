from typing import List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.floor import Floor
from app.schemas.floor import FloorCreate, FloorUpdate


class FloorRepository:
    async def create(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        floor_in: FloorCreate,
    ) -> Floor:
        floor = Floor(
            space_id=space_id,
            floor_number=floor_in.floor_number,
            title=floor_in.title,
            ppm=floor_in.ppm,
        )
        db.add(floor)
        await db.flush()
        return floor

    async def get_by_id(
        self,
        db: AsyncSession,
        floor_id: uuid.UUID,
    ) -> Optional[Floor]:
        stmt = select(Floor).where(Floor.id == floor_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_space_and_number(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        floor_number: int,
    ) -> Optional[Floor]:
        stmt = select(Floor).where(
            Floor.space_id == space_id,
            Floor.floor_number == floor_number,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_space(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> List[Floor]:
        stmt = (
            select(Floor)
            .where(Floor.space_id == space_id)
            .order_by(Floor.floor_number.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        db: AsyncSession,
        floor: Floor,
        floor_in: FloorUpdate,
    ) -> Floor:
        if floor_in.floor_number is not None:
            floor.floor_number = floor_in.floor_number
        if floor_in.title is not None:
            floor.title = floor_in.title
        if floor_in.ppm is not None:
            floor.ppm = floor_in.ppm
        if floor_in.width_px is not None:
            floor.width_px = floor_in.width_px
        if floor_in.height_px is not None:
            floor.height_px = floor_in.height_px
        if floor_in.plan_original_key is not None:
            floor.plan_original_key = floor_in.plan_original_key
        if floor_in.plan_optimized_key is not None:
            floor.plan_optimized_key = floor_in.plan_optimized_key
        if floor_in.plan_tiles_prefix is not None:
            floor.plan_tiles_prefix = floor_in.plan_tiles_prefix
        if floor_in.layout_data is not None:
            floor.layout_data = floor_in.layout_data
        await db.flush()
        return floor


floor_repo = FloorRepository()
