from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.core.exceptions import StorageError


class S3ObjectStorage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    async def download(self, object_key: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(
                self.client.download_file,
                self.bucket,
                object_key,
                str(destination),
            )
        except Exception as exc:
            raise StorageError(f"Failed to download object: {object_key}") from exc
        return destination

    async def upload(self, source: Path, object_key: str, *, content_type: str | None = None) -> str:
        extra_args = {"ContentType": content_type} if content_type else None
        try:
            await asyncio.to_thread(
                self.client.upload_file,
                str(source),
                self.bucket,
                object_key,
                ExtraArgs=extra_args or {},
            )
        except Exception as exc:
            raise StorageError(f"Failed to upload object: {object_key}") from exc
        return object_key

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        try:
            response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=object_key)
            body = response["Body"]
            while chunk := await asyncio.to_thread(body.read, 1024 * 1024):
                yield chunk
        except Exception as exc:
            raise StorageError(f"Failed to stream object: {object_key}") from exc

    async def exists(self, object_key: str) -> bool:
        try:
            await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=object_key)
            return True
        except Exception:
            return False
