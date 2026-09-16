from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "parking",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.maintenance", "app.tasks.reports"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.APP_TIMEZONE,
    enable_utc=True,
)