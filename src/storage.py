from __future__ import annotations

import os
import uuid
from pathlib import Path

from src.logger import logger

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mov", ".avi", ".webm",
    ".pdf", ".doc", ".docx",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
def _get_r2_client():
    endpoint = os.getenv("ATTACHMENTS_R2_ENDPOINT_URL")
    access_key = os.getenv("ATTACHMENTS_R2_ACCESS_KEY_ID")
    secret_key = os.getenv("ATTACHMENTS_R2_SECRET_ACCESS_KEY")

    if not all([endpoint, access_key, secret_key]):
        return None

    try:
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )
    except ImportError:
        logger.warning("boto3 não instalado, a usar armazenamento local.")
        return None


def validate_file(filename: str, size: int) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Tipo de ficheiro não permitido: {ext}"
    if size > MAX_FILE_SIZE:
        return f"Ficheiro demasiado grande (máx. {MAX_FILE_SIZE // (1024*1024)} MB)"
    return None


def upload_file(file_bytes: bytes, filename: str, content_type: str) -> tuple[str, str | None]:
    ext = Path(filename).suffix.lower()
    storage_key = f"attachments/{uuid.uuid4().hex}{ext}"

    client = _get_r2_client()
    bucket = os.getenv("ATTACHMENTS_R2_BUCKET_NAME")

    if client and bucket:
        try:
            client.put_object(
                Bucket=bucket,
                Key=storage_key,
                Body=file_bytes,
                ContentType=content_type,
            )
            r2_public = os.getenv("ATTACHMENTS_R2_PUBLIC_URL", "")
            url = f"{r2_public}/{bucket}/{storage_key}" if r2_public else None
            logger.info(f"Ficheiro enviado para R2 | key={storage_key}")
            return storage_key, url
        except Exception as e:
            logger.warning(f"Falha no upload R2, a usar local | erro={e}")

    LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    local_path = LOCAL_UPLOAD_DIR / storage_key.replace("/", os.sep)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    with open(local_path, "wb") as f:
        f.write(file_bytes)

    logger.info(f"Ficheiro guardado localmente | path={local_path}")
    return storage_key, f"/uploads/{storage_key}"
