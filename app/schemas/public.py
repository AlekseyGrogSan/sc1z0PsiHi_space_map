from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


class PublicPOIPhotoRead(BaseModel):
    """Публичная схема фотографии POI (только URL и порядок)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sort_order: int
    storage_key: str = Field(exclude=True)

    @computed_field
    def url(self) -> str:
        return f"{settings.S3_PUBLIC_URL_PREFIX}/{self.storage_key}"


class PublicPOIRead(BaseModel):
    """Публичная схема точки интереса (лёгкая, для мобильного клиента)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    title: str
    category: str
    description: Optional[str] = None
    x_coord: float
    y_coord: float
    panorama_id: Optional[uuid.UUID] = None
    photos: List[PublicPOIPhotoRead] = Field(default_factory=list)

    @computed_field
    def x(self) -> float:
        return self.x_coord

    @computed_field
    def y(self) -> float:
        return self.y_coord


class PublicFloorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_number: int
    title: str
    plan_optimized_key: Optional[str] = Field(None, exclude=True)
    plan_original_key: Optional[str] = Field(None, exclude=True)
    width_px: Optional[int] = Field(None, exclude=True)
    height_px: Optional[int] = Field(None, exclude=True)
    ppm: Optional[float] = None
    pois: List[PublicPOIRead] = Field(default_factory=list)

    @computed_field
    def width(self) -> Optional[int]:
        return self.width_px

    @computed_field
    def height(self) -> Optional[int]:
        return self.height_px

    @computed_field
    def plan_image_url(self) -> Optional[str]:
        key = self.plan_optimized_key or self.plan_original_key
        if not key:
            return None
        return f"{settings.S3_PUBLIC_URL_PREFIX}/{key.lstrip('/')}"

    @computed_field
    def plan_thumb_url(self) -> Optional[str]:
        key = self.plan_optimized_key or self.plan_original_key
        if not key:
            return None
        if "optimized.webp" in key:
            thumb_key = key.replace("optimized.webp", "thumb.webp")
            return f"{settings.S3_PUBLIC_URL_PREFIX}/{thumb_key.lstrip('/')}"
        return f"{settings.S3_PUBLIC_URL_PREFIX}/{key.lstrip('/')}"


class PublicSpaceBundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    description: Optional[str] = None
    is_published: bool = True
    floors: List[PublicFloorRead] = []
    categories: List[str] = Field(
        default=["stand", "wifi", "info", "food", "wc", "stage", "entrance"],
        description="Категории точек интереса",
    )
    settings: Dict[str, Any] = Field(default_factory=dict)

    @computed_field
    def pois(self) -> List[PublicPOIRead]:
        all_pois: List[PublicPOIRead] = []
        for f in self.floors:
            all_pois.extend(f.pois)
        return all_pois


class PublicPOIPhotosResponse(BaseModel):
    """Ответ публичного эндпоинта для получения фотографий POI."""

    poi_id: uuid.UUID
    poi_title: str
    photos: List[PublicPOIPhotoRead] = Field(default_factory=list)