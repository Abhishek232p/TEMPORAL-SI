import hashlib
import logging
import os
from typing import Optional

from fastapi import UploadFile
from vercel.blob import BlobNotFoundError

logger = logging.getLogger(__name__)


class ArtifactStorageError(RuntimeError):
    pass


class VercelBlobStorage:
    driver = "vercel_blob"
    persistence = "durable"
    prefix = "temporal-intelligence"

    def __init__(self, client=None):
        if client is None:
            from vercel.blob import BlobClient

            client = BlobClient()
        self._not_found_error = BlobNotFoundError
        self.client = client

    @staticmethod
    def is_configured() -> bool:
        has_read_write_token = bool(os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip())
        has_oidc_credentials = bool(
            os.environ.get("VERCEL_OIDC_TOKEN", "").strip()
            and os.environ.get("BLOB_STORE_ID", "").strip()
        )
        return has_read_write_token or has_oidc_credentials

    @classmethod
    def artifact_path(
        cls,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        filename: str,
    ) -> str:
        if filename not in {"data.csv", "source.parquet"}:
            raise ValueError("Unsupported artifact filename")
        return (
            f"{cls.prefix}/{org_id}/{project_id}/{dataset_id}/"
            f"{version}/{filename}"
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

        file.file.seek(0)
        source_bytes = file.file.read()
        file.file.seek(0)
        content_hash = hashlib.sha256(source_bytes).hexdigest()
        source_name = "source.parquet" if is_parquet else "data.csv"
        pending = [
            (
                self.artifact_path(org_id, project_id, dataset_id, version, source_name),
                source_bytes,
                "application/vnd.apache.parquet" if is_parquet else "text/csv",
            )
        ]
        if is_parquet:
            pending.append(
                (
                    self.artifact_path(org_id, project_id, dataset_id, version, "data.csv"),
                    normalized_csv,
                    "text/csv",
                )
            )

        uploaded_paths = []
        try:
            for path, content, content_type in pending:
                self.client.put(
                    path,
                    content,
                    access="private",
                    content_type=content_type,
                    multipart=len(content) > 5 * 1024 * 1024,
                )
                uploaded_paths.append(path)
        except Exception as error:
            if uploaded_paths:
                try:
                    self.client.delete(uploaded_paths)
                except Exception:
                    logger.exception("Could not roll back an incomplete Vercel Blob upload")
                    raise ArtifactStorageError(
                        "Artifact upload failed and incomplete blob cleanup also failed"
                    ) from error
            raise ArtifactStorageError("Artifact upload to Vercel Blob failed") from error

        return content_hash

    def read_artifact(
        self,
        org_id: str,
        project_id: str,
        dataset_id: str,
        version: int,
        filename: str = "data.csv",
    ) -> Optional[bytes]:
        path = self.artifact_path(org_id, project_id, dataset_id, version, filename)
        try:
            result = self.client.get(path, access="private")
        except Exception as error:
            if self._not_found_error and isinstance(error, self._not_found_error):
                return None
            raise ArtifactStorageError("Could not read artifact from Vercel Blob") from error
        if result is None:
            return None
        if result.status_code != 200:
            raise ArtifactStorageError(
                f"Vercel Blob returned unexpected status {result.status_code}"
            )
        return result.content

    def check_health(self) -> None:
        marker = f"{self.prefix}/_health-check"
        try:
            try:
                result = self.client.get(marker, access="private")
            except Exception as error:
                if not self._not_found_error or not isinstance(error, self._not_found_error):
                    raise
                self.client.put(
                    marker,
                    b"ok",
                    access="private",
                    content_type="text/plain",
                    overwrite=True,
                )
                result = self.client.get(marker, access="private")
            if result is None or result.status_code != 200:
                raise ArtifactStorageError("Vercel Blob health marker could not be read")
        except ArtifactStorageError:
            raise
        except Exception as error:
            raise ArtifactStorageError("Vercel Blob connectivity check failed") from error
