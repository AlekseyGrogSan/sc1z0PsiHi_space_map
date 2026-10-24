from typing import List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.orm import joinedload

from app.models.floor import Floor
from app.models.poi import POI, POIPhoto
from app.models.space import Space, SpaceMember, SpaceRole
from app.schemas.space import SpaceCreate, SpaceUpdate


class SpaceRepository:
    async def create(
        self,
        db: AsyncSession,
        space_in: SpaceCreate,
        owner_id: uuid.UUID,
    ) -> Space:
        space = Space(
            title=space_in.title,
            slug=space_in.slug.lower().strip(),
            description=space_in.description,
            is_published=False,
            settings=space_in.settings or {},
        )
        db.add(space)
        await db.flush()

        member = SpaceMember(
            space_id=space.id,
            user_id=owner_id,
            role=SpaceRole.OWNER,
        )
        db.add(member)
        await db.flush()

        # Reload with floors
        return await self.get_by_id(db, space.id)  # type: ignore

    async def get_by_id(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Optional[Space]:
        stmt = (
            select(Space)
            .where(Space.id == space_id)
            .options(selectinload(Space.floors))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Optional[Space]:
        stmt = (
            select(Space)
            .where(Space.slug == slug.lower().strip())
            .options(selectinload(Space.floors))
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_public_bundle_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Optional[Space]:
        """
        Загружает пространство для публичного просмотра, включая этажи,
        POI на каждом этаже и фотографии для каждого POI.
        """
        stmt = (
            select(Space)
            .where(Space.slug == slug.lower().strip())
            .options(
                selectinload(Space.floors)
                .selectinload(Floor.pois)  # type: ignore[attr-defined]
                .selectinload(POI.photos),  # type: ignore[attr-defined]
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(
        self,
        db: AsyncSession,
        space: Space,
        space_in: SpaceUpdate,
    ) -> Space:
        if space_in.title is not None:
            space.title = space_in.title
        if space_in.slug is not None:
            space.slug = space_in.slug.lower().strip()
        if space_in.description is not None:
            space.description = space_in.description
        if space_in.settings is not None:
            space.settings = space_in.settings

        await db.flush()
        return space

    async def set_publish_status(
        self,
        db: AsyncSession,
        space: Space,
        is_published: bool,
    ) -> Space:
        space.is_published = is_published
        await db.flush()
        return space

    async def get_member(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[SpaceMember]:
        stmt = select(SpaceMember).where(
            SpaceMember.space_id == space_id,
            SpaceMember.user_id == user_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_or_update_member(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        user_id: uuid.UUID,
        role: SpaceRole,
    ) -> SpaceMember:
        member = await self.get_member(db, space_id, user_id)
        if member:
            member.role = role
        else:
            member = SpaceMember(
                space_id=space_id,
                user_id=user_id,
                role=role,
            )
            db.add(member)
        await db.flush()
        return member

    async def list_members(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> List[SpaceMember]:
        stmt = (
            select(SpaceMember)
            .where(SpaceMember.space_id == space_id)
            .options(selectinload(SpaceMember.user))
            .order_by(SpaceMember.created_at.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


    async def list_all(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Space]:
        stmt = (
            select(Space)
            .options(selectinload(Space.floors))
            .order_by(Space.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Space]:
        stmt = (
            select(Space)
            .join(SpaceMember, SpaceMember.space_id == Space.id)
            .where(SpaceMember.user_id == user_id)
            .options(selectinload(Space.floors))
            .order_by(Space.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def delete(
        self,
        db: AsyncSession,
        space: Space,
    ) -> None:
        await db.delete(space)
        await db.flush()


space_repo = SpaceRepository()
