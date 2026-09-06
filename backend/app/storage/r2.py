"""Cloudflare R2 (S3-compatible) storage.

Uploads never pass through the API: the browser PUTs directly to R2 with a
presigned URL. The presigned PUT signs the Content-Type, so the browser
must send exactly the Content-Type it requested the URL for. Bucket CORS
must allow PUT from the frontend origin (see docs/setup-r2.md).
"""

import uuid

import boto3
from botocore.config import Config

from app.config import settings


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def object_key(user_id: str, filename: str) -> str:
    """Namespaced, collision-free key: documents/<user>/<uuid>/<filename>."""
    return f"documents/{user_id}/{uuid.uuid4()}/{filename}"


def presign_put(key: str, content_type: str, expires_seconds: int = 600) -> str:
    return r2_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.r2_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_seconds,
    )


def download_bytes(key: str) -> bytes:
    obj = r2_client().get_object(Bucket=settings.r2_bucket, Key=key)
    return obj["Body"].read()


def delete_object(key: str) -> None:
    r2_client().delete_object(Bucket=settings.r2_bucket, Key=key)
