from pathlib import Path

import pytest

from app.core.exceptions import StorageError
from app.storage.local import LocalObjectStorage


async def test_local_storage_upload_and_download(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")
    source = tmp_path / "source.txt"
    source.write_text("onramp", encoding="utf-8")

    await storage.upload(source, "tenant/job/source.txt")
    destination = tmp_path / "downloaded.txt"
    await storage.download("tenant/job/source.txt", destination)

    assert destination.read_text(encoding="utf-8") == "onramp"


async def test_local_storage_rejects_parent_traversal(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "objects")

    with pytest.raises(StorageError, match="escapes"):
        await storage.exists("../secret.txt")
