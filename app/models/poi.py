import enum
import uuid
from typing import Optional
from sqlalchemy import Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class POICategory(str, enum.Enum):
    """Категории точек интереса (фиксированный список MVP)."""

    STAND = "stand"
    WIFI = "wifi"
    WC = "wc"
    INFO = "info"
    FOOD = "food"


class POI(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Точка интереса (POI): стенд, Wi-Fi зона, туалет, стойка информации, кафе.

    Двойная привязка:
    - обязательная: координаты (x_coord, y_coord) на 2D-плане этажа (floor_id);
    - опциональная: панорама (panorama_id) + углы (yaw_in_panorama, pitch_in_panorama)
      для отображения плашки-маркера внутри 360-панорамы.
    """

    __tablename__ = "pois"

    # Обязательная привязка к этажу (при удалении этажа POI удаляются каскадно)
    floor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("floors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Опциональная привязка к панораме (при удалении панорамы POI отвязывается)
    panorama_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("panoramas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[POICategory] = mapped_column(
        Enum(
            POICategory,
            name="poi_category_enum",
            native_enum=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Координаты на 2D-плане этажа (пиксели чертежа, масштаб задает floor.ppm)
    x_coord: Mapped[float] = mapped_column(Float, nullable=False)
    y_coord: Mapped[float] = mapped_column(Float, nullable=False)

    # Углы маркера внутри 360-панорамы: yaw (-180..180), pitch (-90..90)
    yaw_in_panorama: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pitch_in_panorama: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
