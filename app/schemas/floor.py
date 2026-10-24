from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


class FloorBase(BaseModel):
    floor_number: int = Field(..., description="Номер этажа (может быть отрицательным для подвала)")
    title: str = Field(..., min_length=1, max_length=255, description="Название этажа, например '1 этаж'")
    ppm: Optional[float] = Field(None, gt=0, description="Масштаб: пикселей на 1 метр")
    layout_data: Optional[dict] = Field(default_factory=dict, description="2D векторные элементы (комнаты, стены, препятствия)")


class FloorCreate(FloorBase):
    pass


class FloorUpdate(BaseModel):
    floor_number: Optional[int] = None
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    ppm: Optional[float] = Field(None, gt=0)
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    plan_original_key: Optional[str] = None
    plan_optimized_key: Optional[str] = None
    plan_tiles_prefix: Optional[str] = None
    layout_data: Optional[dict] = None


class FloorRead(FloorBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    space_id: uuid.UUID
    plan_original_key: Optional[str] = None
    plan_optimized_key: Optional[str] = None
    plan_tiles_prefix: Optional[str] = None
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    layout_data: Optional[dict] = Field(default_factory=dict)
    created_at: datetime

    @computed_field
    def plan_url(self) -> Optional[str]:
        """Динамический URL оптимизированного чертежа."""
        key = self.plan_optimized_key or self.plan_original_key
        if not key:
            return None
        return f"{settings.S3_PUBLIC_URL_PREFIX}/{key.lstrip('/')}"
