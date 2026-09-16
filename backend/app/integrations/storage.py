import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from minio import Minio

from app.core.config import settings

_client: Minio | None = None
_bucket_checked = False


def get_client() -> Minio:
    global _client, _bucket_checked
    if _client is None:
        _client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
    if not _bucket_checked:
        if not _client.bucket_exists(settings.MINIO_BUCKET):
            _client.make_bucket(settings.MINIO_BUCKET)
        _bucket_checked = True
    return _client


def build_object_key(prefix: str, original_name: str | None) -> str:
    now = datetime.now(timezone.utc)
    ext = "bin"
    if original_name and "." in original_name:
        ext = original_name.rsplit(".", 1)[-1].lower()[:8]
    return f"{prefix}/{now.year}/{now.month:02d}/{now.day:02d}/{uuid.uuid4().hex}.{ext}"


def upload_bytes(data: bytes, prefix: str, original_name: str | None, content_type: str | None) -> dict:
    client = get_client()
    object_key = build_object_key(prefix, original_name)
    size = len(data)
    client.put_object(
        settings.MINIO_BUCKET, object_key,
        data=__import__("io").BytesIO(data), length=size,
        content_type=content_type or "application/octet-stream",
    )
    checksum = hashlib.sha256(data).hexdigest()
    return {"bucket": settings.MINIO_BUCKET, "object_key": object_key,
            "size": size, "checksum": checksum}


def presigned_get(object_key: str, minutes: int | None = None) -> str:
    client = get_client()
    expire = timedelta(minutes=minutes or settings.MINIO_PRESIGN_EXPIRE_MINUTES)
    return client.presigned_get_object(settings.MINIO_BUCKET, object_key, expires=expire)


def delete_object(object_key: str) -> None:
    client = get_client()
    client.remove_object(settings.MINIO_BUCKET, object_key)