import pytest
import pandas as pd
from packages.core.data.profiler import DataProfiler

def test_data_profiler_general():
    df = pd.DataFrame({
        "timestamp": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"],
        "series_id": ["A", "A"],
        "value": [10.5, 20.0],
        "category": ["X", "Y"],
        "null_col": [None, 5.0]
    })
    
    profiler = DataProfiler()
    res = profiler.profile_dataframe(df)
    
    assert res["general_statistics"]["row_count"] == 2
    assert res["general_statistics"]["column_count"] == 5
    assert res["general_statistics"]["columns"]["value"]["mean"] == 15.25
    assert res["general_statistics"]["columns"]["null_col"]["null_count"] == 1
    assert res["general_statistics"]["columns"]["category"]["unique_count"] == 2

def test_data_profiler_temporal():
    df = pd.DataFrame({
        "timestamp": [
            "2026-01-01T00:00:00Z", 
            "2026-01-02T00:00:00Z", 
            "2026-01-04T00:00:00Z"  # gap of 2 days
        ],
        "series_id": ["A", "A", "A"],
        "value": [10.0, 20.0, 30.0]
    })
    
    profiler = DataProfiler()
    res = profiler.profile_dataframe(df)
    
    temp_stats = res["temporal_statistics"]
    assert temp_stats["series_count"] == 1
    assert temp_stats["irregular_series_sample_count"] == 1
    assert temp_stats["duration_seconds"] == 3 * 24 * 3600
