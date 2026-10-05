import pandas as pd
from fastapi import UploadFile
import json
import hashlib

def parse_dataset_metadata(file: UploadFile):
    filename = file.filename.lower()
    
    if filename.endswith(".csv"):
        df = pd.read_csv(file.file)
    elif filename.endswith(".parquet"):
        df = pd.read_parquet(file.file)
    else:
        raise ValueError("Unsupported file format. Must be CSV or Parquet.")
        
    row_count = len(df)
    column_count = len(df.columns)
    
    # Generate a schema hash based on column names and dtypes
    schema_dict = {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)}
    schema_str = json.dumps(schema_dict, sort_keys=True)
    schema_hash = hashlib.sha256(schema_str.encode()).hexdigest()
    
    # Reset file pointer again just in case
    file.file.seek(0)
    
    return {
        "row_count": row_count,
        "column_count": column_count,
        "schema_hash": schema_hash
    }
