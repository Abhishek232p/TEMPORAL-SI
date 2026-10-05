import pandas as pd
import numpy as np
from typing import Dict, Any

class DataProfiler:
    def profile_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        general_stats = self._compute_general_stats(df)
        temporal_stats = {}
        if 'timestamp' in df.columns and 'series_id' in df.columns:
            temporal_stats = self._compute_temporal_stats(df)
            
        return {
            "general_statistics": general_stats,
            "temporal_statistics": temporal_stats
        }

    def _compute_general_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        stats = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "duplicate_rows": int(df.duplicated().sum()),
            "columns": {}
        }
        
        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            null_count = int(series.isnull().sum())
            unique_count = int(series.nunique(dropna=True))
            
            col_stats = {
                "type": dtype,
                "null_count": null_count,
                "null_percentage": round((null_count / len(df)) * 100, 2) if len(df) > 0 else 0,
                "unique_count": unique_count
            }
            
            if pd.api.types.is_numeric_dtype(series):
                col_stats.update({
                    "min": float(series.min()) if not pd.isna(series.min()) else None,
                    "max": float(series.max()) if not pd.isna(series.max()) else None,
                    "mean": float(series.mean()) if not pd.isna(series.mean()) else None,
                    "std": float(series.std()) if not pd.isna(series.std()) else None,
                    "zeros": int((series == 0).sum())
                })
                
            stats["columns"][col] = col_stats
            
        return stats

    def _compute_temporal_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        # Ensure timestamp is datetime
        df = df.copy()
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
        valid_temporal_df = df.dropna(subset=['timestamp', 'series_id'])
        
        series_count = int(valid_temporal_df['series_id'].nunique())
        
        if len(valid_temporal_df) == 0:
            return {"series_count": 0}
            
        min_ts = valid_temporal_df['timestamp'].min()
        max_ts = valid_temporal_df['timestamp'].max()
        duration_seconds = int((max_ts - min_ts).total_seconds()) if pd.notna(min_ts) and pd.notna(max_ts) else 0
        
        # Analyze frequency per series
        irregular_intervals = 0
        gaps = 0
        
        # We sample a few series to avoid memory explosion on huge datasets
        sample_series = valid_temporal_df['series_id'].unique()[:100]
        for sid in sample_series:
            s_df = valid_temporal_df[valid_temporal_df['series_id'] == sid].sort_values('timestamp')
            if len(s_df) > 1:
                diffs = s_df['timestamp'].diff().dropna()
                # If there's more than one unique interval, it's irregular
                if diffs.nunique() > 1:
                    irregular_intervals += 1
                
                # Simple gap detection: diff > 2 * median diff
                median_diff = diffs.median()
                if pd.notna(median_diff) and median_diff.total_seconds() > 0:
                    gaps += int((diffs > 2 * median_diff).sum())
                    
        return {
            "series_count": series_count,
            "min_timestamp": min_ts.isoformat() if pd.notna(min_ts) else None,
            "max_timestamp": max_ts.isoformat() if pd.notna(max_ts) else None,
            "duration_seconds": duration_seconds,
            "irregular_series_sample_count": irregular_intervals,
            "gap_count_sample": gaps
        }
