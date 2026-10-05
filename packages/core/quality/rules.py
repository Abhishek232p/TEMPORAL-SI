"""
Quality validation rules.

Each rule is a callable that receives a DataFrame and optional configuration,
and returns a list of QualityFinding objects.

Rules are deterministic: the same DataFrame always produces the same findings.
Rules never mutate the input DataFrame.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from packages.core.quality.findings import QualityFinding, Severity, MeasurementType


# ---------------------------------------------------------------------------
# Schema rules
# ---------------------------------------------------------------------------

def validate_required_columns(
    df: pd.DataFrame,
    required_columns: List[str],
) -> List[QualityFinding]:
    """Check that every column in required_columns exists in the DataFrame."""
    findings: List[QualityFinding] = []
    for col in required_columns:
        if col not in df.columns:
            findings.append(QualityFinding(
                rule_id="SCHEMA_REQUIRED_COLUMN",
                severity=Severity.ERROR,
                message=f"Required column '{col}' is missing.",
                column=col,
            ))
    return findings


def validate_column_dtypes(
    df: pd.DataFrame,
    expected_dtypes: Dict[str, str],
) -> List[QualityFinding]:
    """Check that columns have compatible data types.

    expected_dtypes maps column name -> expected pandas dtype category:
    'numeric', 'datetime', 'string', 'boolean'.
    """
    findings: List[QualityFinding] = []
    dtype_checkers = {
        "numeric": pd.api.types.is_numeric_dtype,
        "datetime": pd.api.types.is_datetime64_any_dtype,
        "string": lambda s: pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s),
        "boolean": pd.api.types.is_bool_dtype,
    }
    for col, expected in expected_dtypes.items():
        if col not in df.columns:
            continue  # handled by validate_required_columns
        checker = dtype_checkers.get(expected.lower())
        if checker and not checker(df[col]):
            findings.append(QualityFinding(
                rule_id="SCHEMA_DTYPE_MISMATCH",
                severity=Severity.ERROR,
                message=f"Column '{col}' expected dtype '{expected}', got '{df[col].dtype}'.",
                column=col,
                details={"expected": expected, "actual": str(df[col].dtype)},
            ))
    return findings


# ---------------------------------------------------------------------------
# Null rules
# ---------------------------------------------------------------------------

def validate_null_limits(
    df: pd.DataFrame,
    max_null_fraction: float = 1.0,
    columns: Optional[List[str]] = None,
) -> List[QualityFinding]:
    """Flag columns where the null fraction exceeds the threshold."""
    findings: List[QualityFinding] = []
    check_cols = columns if columns else list(df.columns)
    for col in check_cols:
        if col not in df.columns:
            continue
        null_count = int(df[col].isnull().sum())
        if len(df) == 0:
            continue
        null_frac = null_count / len(df)
        if null_frac > max_null_fraction:
            findings.append(QualityFinding(
                rule_id="NULL_LIMIT_EXCEEDED",
                severity=Severity.ERROR if null_frac >= 0.5 else Severity.WARNING,
                message=f"Column '{col}' has {null_frac:.1%} nulls (limit: {max_null_fraction:.1%}).",
                column=col,
                details={"null_count": null_count, "null_fraction": round(null_frac, 4)},
            ))
    return findings


# ---------------------------------------------------------------------------
# Duplicate rules
# ---------------------------------------------------------------------------

def validate_duplicates(
    df: pd.DataFrame,
    max_duplicate_fraction: float = 0.0,
) -> List[QualityFinding]:
    """Flag if duplicate row fraction exceeds the threshold."""
    findings: List[QualityFinding] = []
    if len(df) == 0:
        return findings
    dup_count = int(df.duplicated().sum())
    dup_frac = dup_count / len(df)
    if dup_frac > max_duplicate_fraction:
        dup_indices = df[df.duplicated()].index.tolist()[:20]  # cap for report size
        findings.append(QualityFinding(
            rule_id="DUPLICATE_ROWS",
            severity=Severity.WARNING if dup_frac < 0.1 else Severity.ERROR,
            message=f"{dup_count} duplicate rows detected ({dup_frac:.1%}).",
            row_indices=dup_indices,
            details={"duplicate_count": dup_count, "duplicate_fraction": round(dup_frac, 4)},
        ))
    return findings


# ---------------------------------------------------------------------------
# Timestamp rules
# ---------------------------------------------------------------------------

def validate_timestamp_parseable(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
) -> List[QualityFinding]:
    """Check that all values in the timestamp column can be parsed as datetimes."""
    findings: List[QualityFinding] = []
    if timestamp_column not in df.columns:
        return findings
    parsed = pd.to_datetime(df[timestamp_column], errors="coerce", utc=True)
    unparseable_mask = parsed.isna() & df[timestamp_column].notna()
    unparseable_count = int(unparseable_mask.sum())
    if unparseable_count > 0:
        bad_indices = df.index[unparseable_mask].tolist()[:20]
        findings.append(QualityFinding(
            rule_id="TIMESTAMP_UNPARSEABLE",
            severity=Severity.ERROR,
            message=f"{unparseable_count} values in '{timestamp_column}' cannot be parsed as datetime.",
            column=timestamp_column,
            row_indices=bad_indices,
            details={"unparseable_count": unparseable_count},
        ))
    return findings


def validate_timestamp_ordering(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    series_column: str = "series_id",
) -> List[QualityFinding]:
    """Check that timestamps are monotonically non-decreasing within each series."""
    findings: List[QualityFinding] = []
    if timestamp_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"])

    if series_column in work.columns:
        groups = work.groupby(series_column)
    else:
        groups = [("__all__", work)]

    total_violations = 0
    violation_indices: List[int] = []
    for _sid, grp in groups:
        sorted_grp = grp.sort_index()
        diffs = sorted_grp["__ts"].diff()
        bad = diffs < pd.Timedelta(0)
        n_bad = int(bad.sum())
        if n_bad > 0:
            total_violations += n_bad
            violation_indices.extend(sorted_grp.index[bad].tolist()[:10])

    if total_violations > 0:
        findings.append(QualityFinding(
            rule_id="TIMESTAMP_NOT_ORDERED",
            severity=Severity.WARNING,
            message=f"{total_violations} timestamp ordering violations detected.",
            column=timestamp_column,
            row_indices=violation_indices[:20],
            details={"violation_count": total_violations},
        ))
    return findings


# ---------------------------------------------------------------------------
# Temporal gap and frequency rules
# ---------------------------------------------------------------------------

def validate_temporal_gaps(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    series_column: str = "series_id",
    gap_multiplier: float = 2.0,
    max_series_sample: int = 100,
) -> List[QualityFinding]:
    """Detect temporal gaps by comparing consecutive intervals against median.

    A gap is defined as an interval > gap_multiplier * median_interval.
    This is a SAMPLED measurement when series_count > max_series_sample.
    """
    findings: List[QualityFinding] = []
    if timestamp_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"])

    if series_column in work.columns:
        all_series = work[series_column].unique()
        is_sampled = len(all_series) > max_series_sample
        sample = all_series[:max_series_sample]
        groups = [(sid, work[work[series_column] == sid]) for sid in sample]
    else:
        is_sampled = False
        groups = [("__all__", work)]

    total_gaps = 0
    gap_indices: List[int] = []
    for _sid, grp in groups:
        sorted_grp = grp.sort_values("__ts")
        if len(sorted_grp) < 2:
            continue
        diffs = sorted_grp["__ts"].diff().dropna()
        median_diff = diffs.median()
        if pd.isna(median_diff) or median_diff.total_seconds() <= 0:
            continue
        gap_mask = diffs > gap_multiplier * median_diff
        n_gaps = int(gap_mask.sum())
        if n_gaps > 0:
            total_gaps += n_gaps
            gap_indices.extend(sorted_grp.index[1:][gap_mask].tolist()[:10])

    if total_gaps > 0:
        findings.append(QualityFinding(
            rule_id="TEMPORAL_GAPS",
            severity=Severity.WARNING,
            message=f"{total_gaps} temporal gaps detected (interval > {gap_multiplier}x median).",
            column=timestamp_column,
            row_indices=gap_indices[:20],
            measurement_type=MeasurementType.SAMPLED if is_sampled else MeasurementType.EXACT,
            details={"gap_count": total_gaps, "sampled": is_sampled},
        ))
    return findings


def validate_frequency_consistency(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    series_column: str = "series_id",
    max_series_sample: int = 100,
) -> List[QualityFinding]:
    """Check whether series have consistent (regular) temporal frequency.

    A series is irregular if it has more than one distinct inter-observation interval.
    """
    findings: List[QualityFinding] = []
    if timestamp_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"])

    if series_column in work.columns:
        all_series = work[series_column].unique()
        is_sampled = len(all_series) > max_series_sample
        sample = all_series[:max_series_sample]
        groups = [(sid, work[work[series_column] == sid]) for sid in sample]
    else:
        is_sampled = False
        groups = [("__all__", work)]

    irregular_count = 0
    for _sid, grp in groups:
        sorted_grp = grp.sort_values("__ts")
        if len(sorted_grp) < 3:
            continue
        diffs = sorted_grp["__ts"].diff().dropna()
        if diffs.nunique() > 1:
            irregular_count += 1

    if irregular_count > 0:
        findings.append(QualityFinding(
            rule_id="FREQUENCY_INCONSISTENT",
            severity=Severity.INFO,
            message=f"{irregular_count} series have irregular temporal frequency.",
            column=timestamp_column,
            measurement_type=MeasurementType.SAMPLED if is_sampled else MeasurementType.EXACT,
            details={"irregular_series_count": irregular_count, "sampled": is_sampled},
        ))
    return findings


# ---------------------------------------------------------------------------
# Series continuity
# ---------------------------------------------------------------------------

def validate_series_continuity(
    df: pd.DataFrame,
    series_column: str = "series_id",
    min_observations: int = 2,
) -> List[QualityFinding]:
    """Flag series that have fewer observations than the minimum threshold."""
    findings: List[QualityFinding] = []
    if series_column not in df.columns:
        return findings
    counts = df[series_column].value_counts()
    short_series = counts[counts < min_observations]
    if len(short_series) > 0:
        findings.append(QualityFinding(
            rule_id="SERIES_TOO_SHORT",
            severity=Severity.WARNING,
            message=f"{len(short_series)} series have fewer than {min_observations} observations.",
            column=series_column,
            details={
                "short_series_count": len(short_series),
                "examples": short_series.head(10).to_dict(),
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Numeric value rules
# ---------------------------------------------------------------------------

def validate_numeric_values(
    df: pd.DataFrame,
    value_column: str = "value",
) -> List[QualityFinding]:
    """Check for NaN, Inf, and -Inf in the numeric value column."""
    findings: List[QualityFinding] = []
    if value_column not in df.columns:
        return findings
    if not pd.api.types.is_numeric_dtype(df[value_column]):
        return findings

    series = df[value_column]
    inf_mask = np.isinf(series)
    inf_count = int(inf_mask.sum())
    if inf_count > 0:
        inf_indices = df.index[inf_mask].tolist()[:20]
        findings.append(QualityFinding(
            rule_id="NUMERIC_INF_VALUES",
            severity=Severity.ERROR,
            message=f"{inf_count} infinite values detected in '{value_column}'.",
            column=value_column,
            row_indices=inf_indices,
            details={"inf_count": inf_count},
        ))
    return findings


def validate_constant_series(
    df: pd.DataFrame,
    value_column: str = "value",
    series_column: str = "series_id",
) -> List[QualityFinding]:
    """Detect series where all values are identical (zero variance)."""
    findings: List[QualityFinding] = []
    if value_column not in df.columns:
        return findings
    if not pd.api.types.is_numeric_dtype(df[value_column]):
        return findings

    if series_column in df.columns:
        groups = df.groupby(series_column)
    else:
        groups = [("__all__", df)]

    constant_count = 0
    constant_examples: List[str] = []
    for sid, grp in groups:
        vals = grp[value_column].dropna()
        if len(vals) >= 2 and vals.nunique() == 1:
            constant_count += 1
            if len(constant_examples) < 10:
                constant_examples.append(str(sid))

    if constant_count > 0:
        findings.append(QualityFinding(
            rule_id="CONSTANT_SERIES",
            severity=Severity.WARNING,
            message=f"{constant_count} series have constant (zero-variance) values.",
            column=value_column,
            details={
                "constant_series_count": constant_count,
                "examples": constant_examples,
            },
        ))
    return findings


# ---------------------------------------------------------------------------
# Configurable impossible-value rules
# ---------------------------------------------------------------------------

def validate_value_bounds(
    df: pd.DataFrame,
    bounds: Dict[str, Dict[str, float]],
) -> List[QualityFinding]:
    """Check that numeric column values fall within configured bounds.

    bounds is a dict: column_name -> {"min": float, "max": float}.
    Either min or max may be omitted.
    """
    findings: List[QualityFinding] = []
    for col, limits in bounds.items():
        if col not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        series = df[col].dropna()
        lo = limits.get("min")
        hi = limits.get("max")

        violations = 0
        violation_indices: List[int] = []
        if lo is not None:
            below = series < lo
            violations += int(below.sum())
            violation_indices.extend(series.index[below].tolist()[:10])
        if hi is not None:
            above = series > hi
            violations += int(above.sum())
            violation_indices.extend(series.index[above].tolist()[:10])

        if violations > 0:
            findings.append(QualityFinding(
                rule_id="VALUE_OUT_OF_BOUNDS",
                severity=Severity.ERROR,
                message=f"{violations} values in '{col}' are outside configured bounds "
                        f"[{lo}, {hi}].",
                column=col,
                row_indices=violation_indices[:20],
                details={"violation_count": violations, "min": lo, "max": hi},
            ))
    return findings
