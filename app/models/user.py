import enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.space import SpaceMember


class SystemRole(str, enum.Enum):
    SUPERADMIN = "superadmin"
    ORGANIZER = "organizer"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    system_role: Mapped[SystemRole] = mapped_column(
        Enum(SystemRole, name="system_role_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=SystemRole.ORGANIZER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    spaces: Mapped[List["SpaceMember"]] = relationship(
        "SpaceMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
