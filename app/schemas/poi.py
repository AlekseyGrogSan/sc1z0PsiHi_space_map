import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.poi import POICategory


class POICreate(BaseModel):
    """Создание точки интереса. floor_id берется из пути эндпоинта."""

    title: str = Field(..., min_length=1, max_length=255, description="Название точки, например 'Стенд ТТК'")
    category: POICategory = Field(..., description="Категория: stand, wifi, wc, info, food")
    description: Optional[str] = Field(None, description="Описание для карточки точки")
    x_coord: float = Field(..., description="Координата X на 2D-плане этажа (px)")
    y_coord: float = Field(..., description="Координата Y на 2D-плане этажа (px)")
    panorama_id: Optional[uuid.UUID] = Field(None, description="ID панорамы, в которой видна точка")
    yaw_in_panorama: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Горизонтальный угол маркера в панораме (-180..180)")
    pitch_in_panorama: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Вертикальный угол маркера в панораме (-90..90)")

    @model_validator(mode="after")
    def check_panorama_angles(self) -> "POICreate":
        if self.panorama_id is None and (
            self.yaw_in_panorama is not None or self.pitch_in_panorama is not None
        ):
            raise ValueError(
                "yaw_in_panorama/pitch_in_panorama can only be set together with panorama_id"
            )
        return self


class POIUpdate(BaseModel):
    """
    Частичное обновление POI.

    Привязка к панораме: передать panorama_id (+ опционально углы yaw/pitch).
    Отвязка от панорамы: передать panorama_id=null — углы при этом
    автоматически сбрасываются в null.
    """

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[POICategory] = None
    description: Optional[str] = None
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None
    panorama_id: Optional[uuid.UUID] = None
    yaw_in_panorama: Optional[float] = Field(None, ge=-180.0, le=180.0)
    pitch_in_panorama: Optional[float] = Field(None, ge=-90.0, le=90.0)


class POIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    panorama_id: Optional[uuid.UUID] = None
    title: str
    category: POICategory
    description: Optional[str] = None
    x_coord: float
    y_coord: float
    yaw_in_panorama: Optional[float] = None
    pitch_in_panorama: Optional[float] = None
    created_at: datetime
