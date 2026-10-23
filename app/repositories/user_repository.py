from typing import List, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash, hash_password
from app.models.space import SpaceMember
from app.models.user import SystemRole, User
from app.schemas.user import UserCreate


class UserRepository:
    async def get_by_id(self, db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.lower().strip())
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        db: AsyncSession,
        user_in: UserCreate,
        system_role: SystemRole = SystemRole.ORGANIZER,
    ) -> User:
        hashed_pw = await get_password_hash(user_in.password)
        user = User(
            email=user_in.email.lower().strip(),
            hashed_password=hashed_pw,
            full_name=user_in.full_name,
            system_role=system_role,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        return user

    async def list_users(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> List[User]:
        stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        db: AsyncSession,
        user: User,
        is_active: bool,
    ) -> User:
        user.is_active = is_active
        await db.flush()
        return user

    async def get_user_spaces(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[SpaceMember]:
        stmt = (
            select(SpaceMember)
            .where(SpaceMember.user_id == user_id)
            .options(selectinload(SpaceMember.space))
            .order_by(SpaceMember.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


user_repo = UserRepository()
