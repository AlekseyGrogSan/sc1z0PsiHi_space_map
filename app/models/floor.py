import uuid
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Float, ForeignKey, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.navigation import NavNode
    from app.models.poi import POI
    from app.models.space import Space


class Floor(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "floors"
    __table_args__ = (
        UniqueConstraint("space_id", "floor_number", name="uq_space_floor_number"),
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # 2D Plan S3 storage keys (relative keys, no host stored)
    plan_original_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    plan_optimized_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    plan_tiles_prefix: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Dimensions & Scale
    width_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height_px: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # pixels per meter

    # 2D Vector Layout (rooms, walls, corridors, obstacles)
    layout_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    @property
    def width(self) -> int:
        return self.width_px or 1600

    @property
    def height(self) -> int:
        return self.height_px or 900

    # Relationships
    space: Mapped["Space"] = relationship("Space", back_populates="floors")
    pois: Mapped[List["POI"]] = relationship(
        "POI",
        back_populates="floor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    nav_nodes: Mapped[List["NavNode"]] = relationship(
        "NavNode",
        back_populates="floor",
        cascade="all, delete-orphan",
    )
