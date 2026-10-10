import os
from pathlib import Path
from typing import Optional, Protocol
from fastapi import UploadFile
import hashlib


class ArtifactStorage(Protocol):
    driver: str
    persistence: str

    def save_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        file: UploadFile,
        normalized_csv: Optional[bytes] = None,
    ) -> str: ...

    def read_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        filename: str = "data.csv",
    ) -> Optional[bytes]: ...

    def check_health(self) -> None: ...


class LocalDiskStorage:
    driver = "local"

    def __init__(self, base_path: str = None):
        if base_path is None:
            # Vercel Functions have a read-only filesystem except for /tmp.
            default_base = "/tmp/.storage" if os.environ.get("VERCEL") else ".storage"
            base_path = os.environ.get("STORAGE_PATH", default_base)
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    @property
    def persistence(self) -> str:
        return "ephemeral" if os.environ.get("VERCEL") else "local"

    @staticmethod
    def _filename(filename: str) -> str:
        if filename not in {"data.csv", "source.parquet"}:
            raise ValueError("Unsupported artifact filename")
        return filename

    def _artifact_path(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        filename: str,
    ) -> Path:
        return (
            self.base_path
            / str(org_id)
            / str(project_id)
            / str(dataset_id)
            / str(version)
            / self._filename(filename)
        )

    def save_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        file: UploadFile,
        normalized_csv: Optional[bytes] = None,
    ) -> str:
        is_parquet = bool(file.filename and file.filename.lower().endswith(".parquet"))
        if is_parquet and normalized_csv is None:
            raise ValueError("Parquet uploads require a normalized CSV representation")

        source_path = self._artifact_path(
            org_id,
            project_id,
            dataset_id,
            version,
            "source.parquet" if is_parquet else "data.csv",
        )
        source_path.parent.mkdir(parents=True, exist_ok=True)
        file.file.seek(0)

        sha256_hash = hashlib.sha256()
        with open(source_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                buffer.write(chunk)
                sha256_hash.update(chunk)

        if is_parquet:
            self._artifact_path(
                org_id, project_id, dataset_id, version, "data.csv"
            ).write_bytes(normalized_csv)

        file.file.seek(0)
        return sha256_hash.hexdigest()

    def read_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        filename: str = "data.csv",
    ) -> Optional[bytes]:
        path = self._artifact_path(org_id, project_id, dataset_id, version, filename)
        return path.read_bytes() if path.is_file() else None

    def check_health(self) -> None:
        if not self.base_path.is_dir() or not os.access(self.base_path, os.W_OK):
            raise OSError("Artifact directory is unavailable")
