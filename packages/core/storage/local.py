import os
import shutil
from pathlib import Path
from fastapi import UploadFile
import hashlib

class LocalDiskStorage:
    # Canonical artifact filename for every stored dataset version.
    ARTIFACT_NAME = "data.csv"

    def __init__(self, base_path: str = ".storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def artifact_path(self, org_id: str, project_id: str, dataset_id: str, version: int) -> Path:
        """Single source of truth for the immutable artifact location."""
        return self.base_path / str(org_id) / str(project_id) / str(dataset_id) / str(version) / self.ARTIFACT_NAME

    def save_artifact(self, org_id: str, project_id: str, dataset_id: str, version: int, file: UploadFile) -> str:
        # Immutable path - always normalized to the canonical artifact name so
        # downstream consumers (profiler, quality, causality) can locate it
        # regardless of the original upload filename.
        file_path = self.artifact_path(org_id, project_id, dataset_id, version)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Reset file pointer before reading
        file.file.seek(0)

        sha256_hash = hashlib.sha256()
        with open(file_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                buffer.write(chunk)
                sha256_hash.update(chunk)

        # Reset again for downstream pandas parsing
        file.file.seek(0)

        return sha256_hash.hexdigest()
