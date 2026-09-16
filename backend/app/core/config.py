from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Parking Management System"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_SECRET_KEY: str = "change-me-in-production"
    APP_TIMEZONE: str = "Asia/Tehran"

    DATABASE_URL: str = "postgresql+asyncpg://parking:parking_pass@127.0.0.1:5433/parking_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"
    MAX_UPLOAD_SIZE_MB: int = 10

    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "Admin@1234"

    GATE_API_KEY: str = "gate-dev-key"

    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "parking-files"
    MINIO_SECURE: bool = False
    MINIO_PRESIGN_EXPIRE_MINUTES: int = 15

    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()