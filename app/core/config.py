<<<<<<< HEAD
from typing import List
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App Config
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "Карта пространства (Indoor Navigation)"
    API_V1_STR: str = "/api/v1"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Database Configuration (PostgreSQL 16 + asyncpg)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/indoor_nav_db"

    # MinIO / S3 Configuration
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
=======
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # API
    PROJECT_NAME: str = "Карта пространства (Indoor Navigation)"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/indoor_nav_db"

    # MinIO / S3 Storage
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_REGION: str = "us-east-1"
>>>>>>> d1d319a (feat(media): implement MinIO S3 service, panorama pipeline, cubemap slicer, blurhash, and API routers)
    S3_BUCKET_PUBLIC: str = "spaces-public"
    S3_BUCKET_STAGING: str = "spaces-staging"
    S3_PUBLIC_URL_PREFIX: str = "http://localhost:9000/spaces-public"

<<<<<<< HEAD
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Authentication & Security
    SECRET_KEY: str = "super-secret-jwt-key-change-in-production-ttk-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

=======
    # Security
    SECRET_KEY: str = "hackathon-secret-jwt-key-2026-ttk"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
>>>>>>> d1d319a (feat(media): implement MinIO S3 service, panorama pipeline, cubemap slicer, blurhash, and API routers)

settings = Settings()
