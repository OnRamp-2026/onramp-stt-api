from functools import lru_cache

import boto3

from app.core.config import get_settings
from app.storage.base import ObjectStorage
from app.storage.local import LocalObjectStorage
from app.storage.s3 import S3ObjectStorage


@lru_cache
def get_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.storage_local_root)

    client = boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url or None,
        region_name=settings.storage_region,
        aws_access_key_id=settings.storage_access_key or None,
        aws_secret_access_key=settings.storage_secret_key or None,
    )
    return S3ObjectStorage(client, settings.storage_bucket)
