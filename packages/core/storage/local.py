import os
import shutil
from pathlib import Path
from fastapi import UploadFile
import hashlib

class LocalDiskStorage:
    def __init__(self, base_path: str = ".storage"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        
    def save_artifact(self, org_id: str, project_id: str, dataset_id: str, version: int, file: UploadFile) -> str:
        # Immutable path
        path = self.base_path / str(org_id) / str(project_id) / str(dataset_id) / str(version)
        path.mkdir(parents=True, exist_ok=True)
        
        file_path = path / file.filename
        
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
