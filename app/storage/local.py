from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.exceptions import StorageError


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, object_key: str) -> Path:
        candidate = (self.root / object_key).resolve()
        if not candidate.is_relative_to(self.root):
            raise StorageError("Object key escapes the configured storage root.")
        return candidate

    async def download(self, object_key: str, destination: Path) -> Path:
        source = self.resolve(object_key)
        if not source.is_file():
            raise StorageError(f"Object not found: {object_key}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)
        return destination

    async def upload(self, source: Path, object_key: str, *, content_type: str | None = None) -> str:
        del content_type
        destination = self.resolve(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)
        return object_key

    async def open_stream(self, object_key: str) -> AsyncIterator[bytes]:
        path = self.resolve(object_key)
        if not path.is_file():
            raise StorageError(f"Object not found: {object_key}")
        with path.open("rb") as source:
            while chunk := await asyncio.to_thread(source.read, 1024 * 1024):
                yield chunk

    async def exists(self, object_key: str) -> bool:
        return self.resolve(object_key).is_file()
