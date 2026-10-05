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
