<<<<<<< HEAD
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api_router import api_v1_router
from app.core.config import settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Ensure database schema is created on startup in development
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup resources on shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API для сервиса интерактивных 3D-карт пространств, виртуальных туров и индор-навигации.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
=======
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.media import router as media_router
from app.api.v1.panoramas import router as panoramas_router
from app.core.config import settings
from app.services.s3 import s3_service

logger = logging.getLogger("uvicorn.info")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Проверка и создание бакетов MinIO
    logger.info("Инициализация сервисов и проверка бакетов S3/MinIO...")
    try:
        await s3_service.ensure_buckets_exist()
        logger.info("MinIO бакеты готовы к работе.")
    except Exception as e:
        logger.warning(f"Не удалось инициализировать S3 на старте (проверьте запуск MinIO): {e}")

    yield
    logger.info("Остановка бэкенд сервиса.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Бэкенд сервиса навигации внутри помещений, 2D-планов и виртуального 3D-тура панорам (ТТК).",
    version="1.0.0",
    lifespan=lifespan,
)

# Настройка CORS для мобильных браузеров и веб-клиента
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
>>>>>>> d1d319a (feat(media): implement MinIO S3 service, panorama pipeline, cubemap slicer, blurhash, and API routers)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
# Mount API Routers
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get(
    "/health",
    tags=["System"],
    status_code=status.HTTP_200_OK,
    summary="Health check сервиса",
)
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


@app.get(
    "/",
    tags=["System"],
    include_in_schema=False,
)
async def root() -> JSONResponse:
    return JSONResponse(
        content={
            "service": settings.PROJECT_NAME,
            "status": "online",
            "docs_url": "/docs",
            "api_version": settings.API_V1_STR,
        }
    )
=======
# Подключение роутеров Разработчика 2 (Media Engine & Panoramas)
app.include_router(panoramas_router, prefix=settings.API_V1_PREFIX)
app.include_router(media_router, prefix=settings.API_V1_PREFIX)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "s3_endpoint": settings.S3_ENDPOINT_URL,
    }
>>>>>>> d1d319a (feat(media): implement MinIO S3 service, panorama pipeline, cubemap slicer, blurhash, and API routers)
