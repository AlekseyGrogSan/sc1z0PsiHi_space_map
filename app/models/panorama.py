import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Panorama(Base):
    __tablename__ = "panoramas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    floor_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    x_coord: Mapped[float] = mapped_column(Float, nullable=False)
    y_coord: Mapped[float] = mapped_column(Float, nullable=False)
    initial_heading: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_upload", index=True, nullable=False)
    
    # S3 Object Keys (относительные пути в бакете)
    blurhash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preview_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    original_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cubemap_prefix: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Связи: исходящие стрелки-хотспоты перехода
    hotspots: Mapped[List["PanoramaHotspot"]] = relationship(
        "PanoramaHotspot",
        primaryjoin="Panorama.id == PanoramaHotspot.source_panorama_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

class PanoramaHotspot(Base):
    __tablename__ = "panorama_hotspots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_panorama_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("panoramas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_panorama_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("panoramas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    yaw: Mapped[float] = mapped_column(Float, nullable=False)     # Горизонтальный угол (-180..180)
    pitch: Mapped[float] = mapped_column(Float, nullable=False)   # Вертикальный угол (-90..90)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class UploadSession(Base):
    __tablename__ = "upload_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    panorama_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("panoramas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


