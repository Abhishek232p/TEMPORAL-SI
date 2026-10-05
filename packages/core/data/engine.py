import hashlib
import json
import uuid
import io
import pandas as pd
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from packages.core.db.models import Dataset, DatasetVersion, IngestionJob, IngestionCheckpoint, ProvenanceRecord, AuditLog, DataSource
from packages.core.storage.local import LocalDiskStorage
from packages.core.data.normalizer import normalize_temporal_data
from packages.core.data.connectors.rest import RESTConnector
from packages.core.data.connectors.postgres import PostgreSQLConnector

class IngestionEngine:
    def __init__(self, db: Session, storage: LocalDiskStorage = None):
        self.db = db
        self.storage = storage or LocalDiskStorage()
        
    def _get_connector(self, category: str):
        if category == "REST":
            return RESTConnector()
        elif category == "POSTGRESQL":
            return PostgreSQLConnector()
        raise ValueError(f"Unsupported connector category: {category}")

    def run_ingestion(self, job_id: uuid.UUID):
        job = self.db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if not job or job.status != 'PENDING':
            return
            
        job.status = 'RUNNING'
        job.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        
        try:
            source = self.db.query(DataSource).filter(DataSource.id == job.source_id).first()
            dataset = self.db.query(Dataset).filter(Dataset.id == job.dataset_id).first()
            
            # Fetch checkpoint
            checkpoint = self.db.query(IngestionCheckpoint).filter(
                IngestionCheckpoint.source_id == source.id,
                IngestionCheckpoint.dataset_id == dataset.id
            ).first()
            
            chk_dict = {}
            if checkpoint:
                chk_dict = {
                    "last_successful_timestamp": checkpoint.last_successful_timestamp,
                    "last_successful_cursor": checkpoint.last_successful_cursor
                }
                
            connector = self._get_connector(source.category)
            raw_bytes = connector.fetch(source.metadata_, chk_dict)
            
            # Normalize and Validate Temporal format
            df = normalize_temporal_data(raw_bytes, source.category)
            
            if len(df) == 0:
                # No new data
                job.status = 'SUCCEEDED'
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                job.rows_ingested = 0
                self.db.commit()
                return

            # Compute Hashes
            final_csv_bytes = df.to_csv(index=False).encode('utf-8')
            content_hash = hashlib.sha256(final_csv_bytes).hexdigest()
            
            schema_dict = {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)}
            schema_hash = hashlib.sha256(json.dumps(schema_dict, sort_keys=True).encode()).hexdigest()
            
            # Idempotency Check
            if checkpoint and checkpoint.last_successful_content_hash == content_hash:
                job.status = 'SUCCEEDED'
                job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                job.rows_ingested = 0
                self.db.commit()
                return
                
            # Create DatasetVersion
            latest_version = self.db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).order_by(DatasetVersion.version.desc()).first()
            next_version = (latest_version.version + 1) if latest_version else 1
            
            from fastapi import UploadFile
            from starlette.datastructures import Headers
            
            class DummyFile:
                def __init__(self, b):
                    self.file = io.BytesIO(b)
                    self.filename = "data.csv"
            
            upload_file = UploadFile(filename="data.csv", file=io.BytesIO(final_csv_bytes), headers=Headers({"content-type": "text/csv"}))
            
            stored_hash = self.storage.save_artifact(
                str(dataset.organization_id), 
                str(dataset.project_id), 
                str(dataset.id), 
                next_version, 
                upload_file
            )
            
            version_record = DatasetVersion(
                id=uuid.uuid4(),
                dataset_id=dataset.id,
                organization_id=dataset.organization_id,
                version=next_version,
                content_hash=stored_hash,
                schema_hash=schema_hash,
                row_count=len(df),
                column_count=len(df.columns),
            )
            self.db.add(version_record)
            
            # Provenance
            # Safe config hash
            config_hash = hashlib.sha256(json.dumps(source.metadata_, sort_keys=True).encode()).hexdigest()
            prov = ProvenanceRecord(
                id=uuid.uuid4(),
                dataset_hash=stored_hash,
                dataset_version_id=version_record.id,
                configuration_hash=config_hash,
            )
            self.db.add(prov)
            
            # Update Checkpoint
            if not checkpoint:
                checkpoint = IngestionCheckpoint(
                    id=uuid.uuid4(),
                    dataset_id=dataset.id,
                    source_id=source.id,
                )
                self.db.add(checkpoint)
            
            checkpoint.last_successful_content_hash = stored_hash
            # Extract max timestamp safely
            max_ts = df['timestamp'].max()
            checkpoint.last_successful_timestamp = max_ts.to_pydatetime()
            
            job.status = 'SUCCEEDED'
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.rows_ingested = len(df)
            job.dataset_version_id = version_record.id
            
            self.db.commit()
            
        except Exception as e:
            self.db.rollback()
            job = self.db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
            job.status = 'FAILED'
            job.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.error_message = str(e)
            self.db.commit()
