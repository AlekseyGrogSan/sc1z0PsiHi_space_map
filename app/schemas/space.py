from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.space import SpaceRole
from app.schemas.floor import FloorRead


class SpaceBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Название пространства (ТЦ, отель, выставка)")
    description: Optional[str] = Field(None, description="Описание пространства")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Кастомные настройки пространства")


class SpaceCreate(SpaceBase):
    slug: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern=r"^[a-z0-9_-]+$",
        description="Уникальный URL slug (латиница, цифры, дефис, подчеркивание)",
    )


class SpaceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=2, max_length=100, pattern=r"^[a-z0-9_-]+$")
    description: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class SpacePublishUpdate(BaseModel):
    is_published: bool = Field(..., description="Статус публикации (true - опубликовано, false - черновик)")


class SpaceMemberCreate(BaseModel):
    email: EmailStr = Field(..., description="Email приглашаемого пользователя")
    role: SpaceRole = Field(default=SpaceRole.EDITOR, description="Роль в пространстве (owner, editor, viewer)")


class SpaceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    space_id: uuid.UUID
    user_id: uuid.UUID
    role: SpaceRole
    created_at: datetime
    user_email: Optional[str] = None
    user_full_name: Optional[str] = None


class SpaceRead(SpaceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    is_published: bool
    created_at: datetime
    floors: List[FloorRead] = []
