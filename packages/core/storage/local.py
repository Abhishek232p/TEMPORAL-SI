import os
from pathlib import Path
from typing import Optional
from fastapi import UploadFile
import hashlib

class LocalDiskStorage:
    def __init__(self, base_path: str = None):
        if base_path is None:
            # Vercel Functions have a read-only filesystem except for /tmp.
            default_base = "/tmp/.storage" if os.environ.get("VERCEL") else ".storage"
            base_path = os.environ.get("STORAGE_PATH", default_base)
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
    def save_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        file: UploadFile,
        normalized_csv: Optional[bytes] = None,
    ) -> str:
        # Immutable path
        path = self.base_path / str(org_id) / str(project_id) / str(dataset_id) / str(version)
        path.mkdir(parents=True, exist_ok=True)

        is_parquet = bool(file.filename and file.filename.lower().endswith(".parquet"))
        source_path = path / ("source.parquet" if is_parquet else "data.csv")
        # Reset file pointer before reading
        file.file.seek(0)

        sha256_hash = hashlib.sha256()
        with open(source_path, "wb") as buffer:
            while chunk := file.file.read(8192):
                buffer.write(chunk)
                sha256_hash.update(chunk)

        if is_parquet:
            if normalized_csv is None:
                raise ValueError("Parquet uploads require a normalized CSV representation")
            (path / "data.csv").write_bytes(normalized_csv)

        file.file.seek(0)
        return sha256_hash.hexdigest()
