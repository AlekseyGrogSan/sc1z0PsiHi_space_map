import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings

# --- Hotspot Schemas ---
class PanoramaHotspotCreate(BaseModel):
    source_panorama_id: uuid.UUID
    target_panorama_id: uuid.UUID
    yaw: float = Field(..., ge=-180.0, le=180.0, description="Горизонтальный угол направления перехода (-180..180)")
    pitch: float = Field(default=0.0, ge=-90.0, le=90.0, description="Вертикальный угол (-90..90)")
    title: Optional[str] = Field(default=None, description="Подпись стрелки перехода, например 'Перейти в конференц-зал'")

class PanoramaHotspotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_panorama_id: uuid.UUID
    target_panorama_id: uuid.UUID
    yaw: float
    pitch: float
    title: Optional[str] = None
    created_at: datetime

# --- Panorama CRUD Schemas ---
class PanoramaCreate(BaseModel):
    floor_id: uuid.UUID
    title: str = Field(..., max_length=255, description="Название точки панорамы, например 'Главный вход'")
    x_coord: float = Field(..., description="Координата X на 2D-плане этажа")
    y_coord: float = Field(..., description="Координата Y на 2D-плане этажа")
    initial_heading: float = Field(default=0.0, ge=0.0, le=360.0, description="Компасный азимут камеры (градусы 0..360)")

class PanoramaUpdate(BaseModel):
    title: Optional[str] = None
    x_coord: Optional[float] = None
    y_coord: Optional[float] = None
    initial_heading: Optional[float] = None

class PanoramaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    title: str
    x_coord: float
    y_coord: float
    initial_heading: float
    status: str
    blurhash: Optional[str] = None
    preview_key: Optional[str] = None
    original_key: Optional[str] = None
    cubemap_prefix: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    hotspots: List[PanoramaHotspotResponse] = []

    @computed_field
    def preview_url(self) -> Optional[str]:
        if not self.preview_key:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.preview_key.lstrip('/')}"

    @computed_field
    def original_url(self) -> Optional[str]:
        if not self.original_key:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.original_key.lstrip('/')}"

    @computed_field
    def cubemap_url_template(self) -> Optional[str]:
        if not self.cubemap_prefix:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.cubemap_prefix.lstrip('/')}/{{level}}/{{face}}_{{y}}_{{x}}.webp"

class PanoramaStatusResponse(BaseModel):
    id: uuid.UUID
    status: str
    blurhash: Optional[str] = None
    preview_url: Optional[str] = None
    error_message: Optional[str] = None

# --- Smartphone Stitching Session Schemas ---
class StitchSessionCreate(BaseModel):
    frame_count: int = Field(..., ge=2, le=60, description="Количество кадров круговой серии для сшивки")

class StitchFrameUrl(BaseModel):
    frame_index: int
    upload_url: str
    storage_key: str

class StitchSessionResponse(BaseModel):
    session_id: uuid.UUID
    panorama_id: uuid.UUID
    frames: List[StitchFrameUrl]

# --- Public Mobile Viewer Schema ---
class PanoramaPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    floor_id: uuid.UUID
    title: str
    x_coord: float
    y_coord: float
    initial_heading: float
    blurhash: Optional[str] = None
    
    preview_key: Optional[str] = None
    original_key: Optional[str] = None
    cubemap_prefix: Optional[str] = None
    hotspots: List[PanoramaHotspotResponse] = []

    @computed_field
    def preview_url(self) -> Optional[str]:
        if not self.preview_key:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.preview_key.lstrip('/')}"

    @computed_field
    def original_url(self) -> Optional[str]:
        if not self.original_key:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.original_key.lstrip('/')}"

    @computed_field
    def cubemap_url_template(self) -> Optional[str]:
        if not self.cubemap_prefix:
            return None
        return f"{settings.API_V1_STR}/media/public/{self.cubemap_prefix.lstrip('/')}/{{level}}/{{face}}_{{y}}_{{x}}.webp"
