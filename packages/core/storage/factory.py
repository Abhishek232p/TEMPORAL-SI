from functools import lru_cache

from packages.core.storage.local import ArtifactStorage, LocalDiskStorage
from packages.core.storage.vercel_blob import VercelBlobStorage


@lru_cache(maxsize=1)
def get_artifact_storage() -> ArtifactStorage:
    if VercelBlobStorage.is_configured():
        return VercelBlobStorage()
    return LocalDiskStorage()
