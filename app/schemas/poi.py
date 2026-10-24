import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.core.config import settings
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


# ============================================================================
# POI Photo Gallery Schemas
# ============================================================================


class POIPhotoUploadResponse(BaseModel):
    """Ответ с Presigned S3 PUT URL для загрузки фотографии POI."""

    upload_url: str = Field(..., description="Presigned S3 PUT URL для прямой загрузки")
    storage_key: str = Field(..., description="Относительный S3-ключ файла")
    expires_in_seconds: int = Field(default=900, description="Срок жизни ссылки в секундах")


class POIPhotoConfirmRequest(BaseModel):
    """Подтверждение успешной загрузки фотографии POI в MinIO."""

    storage_key: str = Field(..., description="S3-ключ загруженного файла")


class POIPhotoRead(BaseModel):
    """Схема фотографии POI (с вычисленным полным URL)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    poi_id: uuid.UUID
    storage_key: str
    sort_order: int
    created_at: datetime

    @computed_field
    def url(self) -> str:
        return f"{settings.S3_PUBLIC_URL_PREFIX}/{self.storage_key}"


class POIPhotoReorderRequest(BaseModel):
    """Изменение порядка фотографий в галерее: список photo_ids в новом порядке."""

    photo_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        description="Список ID фотографий в желаемом порядке (слева направо)",
    )


class POIPhotoDeleteResponse(BaseModel):
    """Ответ после удаления фотографии."""

    success: bool = True
    message: str = "Photo deleted successfully"


class POIPhotoListResponse(BaseModel):
    """Список фотографий POI (организаторский эндпоинт)."""

    poi_id: uuid.UUID
    photos: List[POIPhotoRead] = []
