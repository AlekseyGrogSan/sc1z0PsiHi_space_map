from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.public import router as public_router
from app.api.v1.spaces import router as spaces_router
from app.api.v1.panoramas import router as panoramas_router
from app.api.v1.media import router as media_router
from app.api.v1.pois import router as pois_router
from app.api.v1.navigation import router as navigation_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(spaces_router)
api_v1_router.include_router(public_router)
api_v1_router.include_router(panoramas_router)
api_v1_router.include_router(media_router)
api_v1_router.include_router(pois_router)
api_v1_router.include_router(navigation_router)
