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
        self._validate_safe_query(config["query"])
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
