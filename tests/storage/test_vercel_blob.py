import hashlib
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import UploadFile
from vercel.blob import BlobNotFoundError

from packages.core.storage import factory
from packages.core.storage.vercel_blob import ArtifactStorageError, VercelBlobStorage


class FakeBlobClient:
    def __init__(self):
        self.objects = {}
        self.put_calls = []
        self.get_calls = []
        self.fail_path = None

    def put(self, path, content, **options):
        if path == self.fail_path:
            raise RuntimeError("simulated remote failure")
        self.put_calls.append((path, content, options))
        self.objects[path] = content

    def get(self, path, **options):
        self.get_calls.append((path, options))
        if path not in self.objects:
            raise BlobNotFoundError()
        return SimpleNamespace(status_code=200, content=self.objects[path])

    def delete(self, paths):
        for path in paths:
            self.objects.pop(path, None)


def test_vercel_blob_uploads_private_csv_and_reads_it_back():
    content = b"timestamp,value\n2026-01-01,10\n"
    client = FakeBlobClient()
    storage = VercelBlobStorage(client)
    upload = UploadFile(filename="series.csv", file=BytesIO(content))

    content_hash = storage.save_artifact("org", "project", "dataset", 1, upload)

    expected_path = "temporal-intelligence/org/project/dataset/1/data.csv"
    assert content_hash == hashlib.sha256(content).hexdigest()
    assert client.put_calls[0] == (
        expected_path,
        content,
        {
            "access": "private",
            "content_type": "text/csv",
            "multipart": False,
        },
    )
    assert storage.read_artifact("org", "project", "dataset", 1) == content
    assert client.get_calls[-1] == (expected_path, {"access": "private"})
    assert upload.file.tell() == 0


def test_vercel_blob_keeps_parquet_source_and_normalized_csv():
    parquet = b"parquet-source"
    normalized = b"timestamp,value\n2026-01-01,10\n"
    client = FakeBlobClient()
    storage = VercelBlobStorage(client)
    upload = UploadFile(filename="series.parquet", file=BytesIO(parquet))

    storage.save_artifact(
        "org",
        "project",
        "dataset",
        3,
        upload,
        normalized_csv=normalized,
    )

    assert [call[0] for call in client.put_calls] == [
        "temporal-intelligence/org/project/dataset/3/source.parquet",
        "temporal-intelligence/org/project/dataset/3/data.csv",
    ]
    assert client.objects["temporal-intelligence/org/project/dataset/3/source.parquet"] == parquet
    assert client.objects["temporal-intelligence/org/project/dataset/3/data.csv"] == normalized
    assert all(call[2]["access"] == "private" for call in client.put_calls)


def test_vercel_blob_rolls_back_partial_parquet_upload():
    client = FakeBlobClient()
    second_path = "temporal-intelligence/org/project/dataset/1/data.csv"
    client.fail_path = second_path
    storage = VercelBlobStorage(client)
    upload = UploadFile(filename="series.parquet", file=BytesIO(b"parquet"))

    with pytest.raises(ArtifactStorageError, match="upload to Vercel Blob failed"):
        storage.save_artifact(
            "org",
            "project",
            "dataset",
            1,
            upload,
            normalized_csv=b"timestamp,value\n",
        )

    assert client.objects == {}
    assert upload.file.tell() == 0


def test_vercel_blob_requires_normalized_parquet_before_upload():
    client = FakeBlobClient()
    storage = VercelBlobStorage(client)
    upload = UploadFile(filename="series.parquet", file=BytesIO(b"parquet"))

    with pytest.raises(ValueError, match="normalized CSV"):
        storage.save_artifact("org", "project", "dataset", 1, upload)

    assert client.put_calls == []


def test_vercel_blob_health_check_uses_private_store_access():
    client = FakeBlobClient()
    storage = VercelBlobStorage(client)

    storage.check_health()

    marker = "temporal-intelligence/_health-check"
    assert client.get_calls == [(marker, {"access": "private"})] * 2
    assert client.put_calls == [
        (
            marker,
            b"ok",
            {
                "access": "private",
                "content_type": "text/plain",
                "overwrite": True,
            },
        )
    ]
    assert client.objects[marker] == b"ok"


def test_missing_vercel_blob_artifact_is_reported_as_missing():
    storage = VercelBlobStorage(FakeBlobClient())

    assert storage.read_artifact("org", "project", "dataset", 99) is None


def test_vercel_blob_selects_oidc_or_read_write_token(monkeypatch):
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.delenv("BLOB_STORE_ID", raising=False)
    monkeypatch.delenv("VERCEL_OIDC_TOKEN", raising=False)
    assert not VercelBlobStorage.is_configured()

    monkeypatch.setenv("BLOB_STORE_ID", "store-id")
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "short-lived-token")
    assert VercelBlobStorage.is_configured()

    monkeypatch.delenv("VERCEL_OIDC_TOKEN")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "read-write-token")
    assert VercelBlobStorage.is_configured()


def test_storage_factory_selects_blob_when_credentials_are_configured(monkeypatch):
    class ConfiguredBlobStorage:
        @staticmethod
        def is_configured():
            return True

    monkeypatch.setattr(factory, "VercelBlobStorage", ConfiguredBlobStorage)
    factory.get_artifact_storage.cache_clear()
    try:
        assert isinstance(factory.get_artifact_storage(), ConfiguredBlobStorage)
    finally:
        factory.get_artifact_storage.cache_clear()
