import os

base_dir = r"C:\Users\abhis\.gemini\antigravity-ide\scratch\temporal-intelligence"

def write_file(path, content):
    full_path = os.path.join(base_dir, path)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content.lstrip())

# 1. Update Models
models_update = """
class IngestionJob(Base):
    __tablename__ = 'ingestion_jobs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('data_sources.id', ondelete='CASCADE'), nullable=False)
    status = Column(String, default='PENDING') # PENDING, RUNNING, SUCCEEDED, FAILED
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(String)
    rows_ingested = Column(Integer)
    dataset_version_id = Column(UUID(as_uuid=True), ForeignKey('dataset_versions.id', ondelete='SET NULL'))
    created_at = Column(DateTime, default=datetime.utcnow)

class IngestionCheckpoint(Base):
    __tablename__ = 'ingestion_checkpoints'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey('data_sources.id', ondelete='CASCADE'), nullable=False)
    last_successful_timestamp = Column(DateTime)
    last_successful_cursor = Column(String)
    last_successful_content_hash = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
"""
with open(os.path.join(base_dir, "packages/core/db/models.py"), "a", encoding="utf-8") as f:
    f.write("\n" + models_update.lstrip())

# 2. Connectors Base
connectors_base = """
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class DataConnector(ABC):
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        pass
        
    @abstractmethod
    def fetch(self, config: Dict[str, Any], checkpoint: Optional[Dict[str, Any]] = None) -> Any:
        # Should return raw bytes or an iterator of chunks/rows
        pass
        
    @abstractmethod
    def get_connector_type(self) -> str:
        pass
"""
write_file("packages/core/data/connectors/base.py", connectors_base)

# 3. REST Connector
connectors_rest = """
import httpx
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import ipaddress
import socket
from .base import DataConnector

class SecurityError(Exception):
    pass

class RESTConnector(DataConnector):
    def get_connector_type(self) -> str:
        return "REST"
        
    def _validate_url_ssrf(self, url_str: str):
        parsed = urlparse(url_str)
        if parsed.scheme not in ["http", "https"]:
            raise SecurityError(f"Unsupported scheme: {parsed.scheme}. Only http/https are allowed.")
            
        hostname = parsed.hostname
        if not hostname:
            raise SecurityError("Invalid URL format.")
            
        try:
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_reserved:
                # We might want to allow localhost for testing, but per spec:
                # "reject unsafe localhost/private-network targets by default"
                # If we need it for testing, we can check an environment variable.
                import os
                if os.environ.get("ALLOW_LOCAL_REST") != "1":
                    raise SecurityError(f"Target resolves to unsafe internal IP: {ip}")
        except Exception as e:
            if isinstance(e, SecurityError):
                raise
            raise SecurityError(f"DNS resolution failed: {e}")

    def validate_config(self, config: Dict[str, Any]) -> bool:
        url = config.get("url")
        if not url:
            return False
        self._validate_url_ssrf(url)
        return True

    def fetch(self, config: Dict[str, Any], checkpoint: Optional[Dict[str, Any]] = None) -> Any:
        url = config.get("url")
        method = config.get("method", "GET")
        headers = config.get("headers", {})
        params = config.get("params", {})
        timeout = config.get("timeout", 10.0)
        
        self._validate_url_ssrf(url)
        
        # Support pagination via cursor from checkpoint
        if checkpoint and checkpoint.get("last_successful_cursor"):
            params["cursor"] = checkpoint["last_successful_cursor"]

        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.request(method, url, headers=headers, params=params)
            
            if resp.is_redirect:
                loc = resp.headers.get("location")
                if loc:
                    self._validate_url_ssrf(loc)
                    resp = client.request(method, loc, headers=headers, params=params)
                    
            if resp.status_code >= 400:
                raise Exception(f"HTTP Error {resp.status_code}: {resp.text[:100]}")
                
            # Limit response size
            content = resp.read()
            if len(content) > config.get("max_size", 50 * 1024 * 1024): # 50MB
                raise SecurityError("Response size limit exceeded")
                
            return content
"""
write_file("packages/core/data/connectors/rest.py", connectors_rest)

# 4. PostgreSQL Connector
connectors_pg = """
from sqlalchemy import create_engine, text
from typing import Dict, Any, Optional
from .base import DataConnector

class PostgreSQLConnector(DataConnector):
    def get_connector_type(self) -> str:
        return "POSTGRESQL"

    def _validate_safe_query(self, query: str):
        q = query.upper()
        # Basic string matching combined with DB permissions
        unsafe = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "CREATE "]
        for keyword in unsafe:
            if keyword in q:
                raise Exception(f"Unsafe operation detected: {keyword}")

    def validate_config(self, config: Dict[str, Any]) -> bool:
        if "connection_string" not in config or "query" not in config:
            return False
        return True

    def fetch(self, config: Dict[str, Any], checkpoint: Optional[Dict[str, Any]] = None) -> Any:
        conn_str = config["connection_string"]
        query = config["query"]
        
        self._validate_safe_query(query)
        
        engine = create_engine(conn_str)
        with engine.connect() as conn:
            # Set read only if supported by dialect
            if engine.dialect.name == "postgresql":
                conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
                
            stmt = text(query)
            params = {}
            if checkpoint and checkpoint.get("last_successful_timestamp"):
                params["checkpoint_ts"] = checkpoint["last_successful_timestamp"]
                
            # We return CSV formatted string to match other pipelines, or JSON
            # For simplicity, convert to pandas then CSV
            import pandas as pd
            df = pd.read_sql_query(stmt, conn, params=params)
            return df.to_csv(index=False).encode('utf-8')
"""
write_file("packages/core/data/connectors/postgres.py", connectors_pg)

# 5. Normalizer
normalizer_code = """
import pandas as pd
import io

def normalize_temporal_data(raw_bytes: bytes, source_type: str) -> pd.DataFrame:
    # Convert raw bytes into a DataFrame
    if source_type in ["CSV", "POSTGRESQL", "REST"]:
        # Assume REST returns CSV or we can parse JSON. If JSON, normalize it.
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes))
        except:
            # Try JSON
            df = pd.read_json(io.BytesIO(raw_bytes))
    elif source_type == "PARQUET":
        df = pd.read_parquet(io.BytesIO(raw_bytes))
    else:
        raise ValueError("Unsupported format for normalization")
        
    # Check Canonical format
    required = ["timestamp", "series_id", "value"]
    if not all(col in df.columns for col in required):
        raise ValueError(f"Missing canonical fields. Required: {required}")
        
    # Normalize timestamp
    try:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    except Exception as e:
        raise ValueError("Invalid timestamp format")
        
    df = df.dropna(subset=['timestamp', 'series_id'])
    
    # Sort for deterministic ordering
    df = df.sort_values(by=['series_id', 'timestamp'])
    
    return df
"""
write_file("packages/core/data/normalizer.py", normalizer_code)

print("Part 1 generation done.")
