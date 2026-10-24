from datetime import datetime
from typing import List, Optional
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.space import SpaceRole
from app.models.user import SystemRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    username: str = Field(..., description="Email пользователя (поле называется username для обратной совместимости)")
    password: str


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    system_role: SystemRole
    is_active: bool
    created_at: datetime


class UserSpaceMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    space_id: uuid.UUID
    space_title: str
    space_slug: str
    role: SpaceRole


class UserProfileRead(UserRead):
    accessible_spaces: List[UserSpaceMembershipRead] = []


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefreshRequest(BaseModel):
    refresh_token: str
