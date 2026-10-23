import enum
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from sqlalchemy import Boolean, Enum, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.floor import Floor
    from app.models.user import User


class SpaceRole(str, enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class Space(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "spaces"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )

    # Relationships
    members: Mapped[List["SpaceMember"]] = relationship(
        "SpaceMember",
        back_populates="space",
        cascade="all, delete-orphan",
    )
    floors: Mapped[List["Floor"]] = relationship(
        "Floor",
        back_populates="space",
        cascade="all, delete-orphan",
        order_by="Floor.floor_number",
    )


class SpaceMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "space_members"
    __table_args__ = (
        UniqueConstraint("space_id", "user_id", name="uq_space_user"),
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[SpaceRole] = mapped_column(
        Enum(SpaceRole, name="space_role_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=SpaceRole.VIEWER,
        nullable=False,
    )

    # Relationships
    space: Mapped["Space"] = relationship("Space", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="spaces")
