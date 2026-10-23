from typing import Optional
from pydantic import BaseModel, Field

class PresignedUploadRequest(BaseModel):
    file_name: str = Field(..., description="Имя исходного файла, например photo.jpg")
    content_type: str = Field(default="image/jpeg", description="MIME-тип (image/jpeg, image/png, image/webp)")
    file_size: Optional[int] = Field(default=None, description="Размер файла в байтах (опционально)")

class PresignedUploadResponse(BaseModel):
    upload_url: str = Field(..., description="Presigned S3 PUT URL для прямой загрузки со смартфона/браузера")
    storage_key: str = Field(..., description="Относительный ключ файла в S3")
    expires_in_seconds: int = Field(default=900, description="Срок жизни ссылки в секундах")

class FloorPlanConfirmRequest(BaseModel):
    storage_key: str = Field(..., description="Ключ загруженного файла плана в S3 staging")
    width_px: Optional[int] = Field(default=None, description="Ширина в пикселях (если вычислена на клиенте)")
    height_px: Optional[int] = Field(default=None, description="Высота в пикселях")

class MediaProcessStatusResponse(BaseModel):
    status: str
    message: Optional[str] = None
