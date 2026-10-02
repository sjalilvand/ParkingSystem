from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Parking Management System"
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_SECRET_KEY: str = "change-me-in-production"
    APP_TIMEZONE: str = "Asia/Tehran"

    DATABASE_URL: str = "postgresql+asyncpg://parking:parking_pass@127.0.0.1:15432/parking_db"
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

    # ------------------------------------------------------------------
    # Audit P0 (سند ارکیده v1.0):
    # EXIT_UNPAID_POLICY: سیاست خروج با بدهی پرداخت‌نشده
    #   (سند بخش ۲۳ «خروج پس از پرداخت» نیازمند تصویب است؛
    #    ALLOW | WARN | DENY — پیش‌فرض WARN = حفظ رفتار فعلی + هشدار)
    # TARIFF_REQUIRE_APPROVAL: تعرفه جدید با وضعیت DRAFT ساخته شود (بخش ۲۳)
    # ENFORCE_GATE_PERMISSIONS: کنترل مجوز عملیات دستی گیت/راهبند در API (بخش ۸)
    # ------------------------------------------------------------------
    EXIT_UNPAID_POLICY: str = "WARN"
    TARIFF_REQUIRE_APPROVAL: bool = True
    ENFORCE_GATE_PERMISSIONS: bool = True
    ENFORCE_FINANCE_PERMISSIONS: bool = True
    ENFORCE_VIOLATIONS_PERMISSIONS: bool = True
    ENFORCE_PARKING_PERMISSIONS: bool = True
    YARD_CAPACITY_TOTAL: int | None = None  # REQ-09-03; None/0 = unlimited


_INSECURE_DEFAULTS = {"change-me-in-production", "gate-dev-key"}


def validate_production_security(s: Settings) -> None:
    """در محیط production اجرا با مقادیر پیش‌فرض ناامن ممنوع است (fail-fast)."""
    if s.APP_ENV.lower() not in ("production", "prod"):
        return
    problems: list[str] = []
    if s.JWT_SECRET_KEY in _INSECURE_DEFAULTS or len(s.JWT_SECRET_KEY) < 32:
        problems.append("JWT_SECRET_KEY")
    if s.APP_SECRET_KEY in _INSECURE_DEFAULTS or len(s.APP_SECRET_KEY) < 32:
        problems.append("APP_SECRET_KEY")
    if s.GATE_API_KEY in _INSECURE_DEFAULTS or len(s.GATE_API_KEY) < 16:
        problems.append("GATE_API_KEY")
    if s.DEFAULT_ADMIN_PASSWORD == "Admin@1234":
        problems.append("DEFAULT_ADMIN_PASSWORD")
    if problems:
        raise RuntimeError(
            "SECURITY: مقادیر ناامن پیش‌فرض در محیط production مجاز نیست: "
            + ", ".join(problems)
        )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    validate_production_security(s)
    return s


settings = get_settings()




