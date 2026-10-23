from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


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
    floors: List[PublicFloorRead] = []
    categories: List[str] = Field(
        default=["stand", "wifi", "info", "food", "wc"],
        description="Категории точек интереса",
    )
    settings: Dict[str, Any] = Field(default_factory=dict)
