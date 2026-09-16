from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.exceptions import AppException, NotFoundError
from app.core.system_models import FileRecord
from app.db.session import get_db
from app.modules.identity.models import User
from app.integrations import storage

router = APIRouter(prefix="/files", tags=["Files"])

MAX_SIZE = 10 * 1024 * 1024
IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp", "bmp", "gif", "heic")

# امضای باینری فرمت‌های رایج تصویر (سند بخش ۲۵-۵: کنترل نوع واقعی فایل)
_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"BM": "bmp",
}


def _is_image(filename: str | None, content_type: str | None, data: bytes) -> bool:
    """تصویر بودن: امضای باینری، یا content-type تصویری، یا پسوند معتبر."""
    for magic in _MAGIC:
        if data.startswith(magic):
            return True
    if content_type and content_type.startswith("image/"):
        return True
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in IMAGE_EXTENSIONS:
            return True
    return False


@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    client_ref: str | None = Form(default=None),
    prefix: str = Form(default="violations"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Idempotency آپلود آفلاین (سند بخش ۱۳)
    if client_ref:
        existing = (await db.execute(
            select(FileRecord).where(FileRecord.client_ref == client_ref)
        )).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "object_key": existing.object_key,
                    "size": existing.size, "duplicate": True}

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise AppException("حجم فایل بیش از حد مجاز است (۱۰ مگابایت)")
    if len(data) == 0:
        raise AppException("فایل خالی است")
    if not _is_image(file.filename, file.content_type, data):
        raise AppException("فقط فایل تصویری مجاز است",
                           details={"content_type": file.content_type, "name": file.filename})

    info = storage.upload_bytes(data, prefix=prefix.strip("/") or "misc",
                                original_name=file.filename, content_type=file.content_type)
    rec = FileRecord(
        bucket=info["bucket"], object_key=info["object_key"],
        original_name=file.filename, content_type=file.content_type,
        size=info["size"], checksum=info["checksum"], client_ref=client_ref,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {"id": rec.id, "object_key": rec.object_key, "size": rec.size,
            "checksum": rec.checksum, "duplicate": False}


@router.get("/{file_id}/url")
async def file_url(file_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rec = await db.get(FileRecord, file_id)
    if not rec:
        raise NotFoundError("فایل یافت نشد")
    url = storage.presigned_get(rec.object_key)
    return {"id": rec.id, "url": url,
            "expires_in_minutes": 15,
            "generated_at": datetime.now(timezone.utc).isoformat()}