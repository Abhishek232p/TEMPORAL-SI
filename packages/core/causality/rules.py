"""
Temporal causal safety rules — leakage-risk and temporal-safety analysis.

IMPORTANT: This engine does NOT prove causality.

Each rule inspects a DataFrame for specific classes of temporal information
leakage risk or structural temporal violations. Every rule returns a list
of CausalFinding objects, each carrying mandatory CausalEvidence.

Rules are classified as either:

  EXACT      — Structurally provable. False positives are impossible.
               Example: feature_timestamp > observation_timestamp.
               Example: training data temporally overlaps test data.

  HEURISTIC  — Based on statistical signals consistent with a problem.
               False positives are possible. Legitimate features CAN
               trigger these rules.
               Example: high correlation with future target
                        (could be a valid leading indicator).

Rules never mutate the input DataFrame.
Rules are deterministic (given same input, same output).
Rules do NOT perform forecasting, model selection, or evaluation.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from packages.core.causality.findings import (
    CausalFinding,
    CausalEvidence,
    CausalSeverity,
    DetectionType,
    FindingStatus,
)


# ---------------------------------------------------------------------------
# HEURISTIC: Future information leakage suspicion
# ---------------------------------------------------------------------------

def check_future_value_leakage(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    target_column: str = "value",
    feature_columns: Optional[List[str]] = None,
    correlation_threshold: float = 0.95,
) -> List[CausalFinding]:
    """Flag features with suspiciously high correlation to future target values.

    Detection type: HEURISTIC.
    A legitimate leading indicator can naturally correlate with target(t+1).
    This rule raises suspicion, not proof.
    """
    findings: List[CausalFinding] = []
    if timestamp_column not in df.columns or target_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"]).sort_values("__ts")

    if len(work) < 3:
        return findings

    # Create shifted target (future value)
    work["__future_target"] = work[target_column].shift(-1)
    work = work.dropna(subset=["__future_target"])

    if feature_columns is None:
        feature_columns = [
            c for c in df.columns
            if c not in (timestamp_column, target_column, "series_id")
            and pd.api.types.is_numeric_dtype(df[c])
        ]

    for col in feature_columns:
        if col not in work.columns or not pd.api.types.is_numeric_dtype(work[col]):
            continue
        valid = work[[col, "__future_target"]].dropna()
        if len(valid) < 3:
            continue
        if valid[col].std() == 0 or valid["__future_target"].std() == 0:
            continue

        corr = valid[col].corr(valid["__future_target"])
        if pd.notna(corr) and abs(corr) >= correlation_threshold:
            # Confidence is the ratio of actual correlation to the threshold
            confidence = min(abs(corr) / 1.0, 1.0)  # normalized to [0, 1]
            findings.append(CausalFinding(
                rule_id="FUTURE_VALUE_LEAKAGE",
                severity=CausalSeverity.WARNING,
                status=FindingStatus.SUSPECTED,
                detection_type=DetectionType.HEURISTIC,
                confidence=round(confidence, 4),
                message=f"Feature '{col}' has {corr:.3f} correlation with "
                        f"future target — suspected future information leakage. "
                        f"NOTE: This could also be a legitimate leading indicator.",
                column=col,
                evidence=CausalEvidence(
                    description=f"Pearson correlation between '{col}' at time t and "
                                f"'{target_column}' at time t+1 is {corr:.4f}, "
                                f"exceeding the threshold of {correlation_threshold}. "
                                f"This is consistent with future information leakage "
                                f"but could also indicate a genuine predictive signal.",
                    columns_involved=[col, target_column],
                    statistic_name="pearson_correlation_with_future_target",
                    statistic_value=round(corr, 4),
                    threshold=correlation_threshold,
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# HEURISTIC: Target leakage suspicion
# ---------------------------------------------------------------------------

def check_target_leakage(
    df: pd.DataFrame,
    target_column: str = "value",
    feature_columns: Optional[List[str]] = None,
    correlation_threshold: float = 0.99,
    timestamp_column: str = "timestamp",
) -> List[CausalFinding]:
    """Flag features that are near-perfect proxies for the target.

    Detection type: HEURISTIC.
    A legitimate derived feature can be highly correlated with the target
    without being leakage. This rule raises suspicion, not proof.
    """
    findings: List[CausalFinding] = []
    if target_column not in df.columns:
        return findings

    if feature_columns is None:
        feature_columns = [
            c for c in df.columns
            if c not in (target_column, timestamp_column, "series_id")
            and pd.api.types.is_numeric_dtype(df[c])
        ]

    for col in feature_columns:
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        valid = df[[col, target_column]].dropna()
        if len(valid) < 3:
            continue
        if valid[col].std() == 0 or valid[target_column].std() == 0:
            continue

        corr = valid[col].corr(valid[target_column])
        if pd.notna(corr) and abs(corr) >= correlation_threshold:
            confidence = min(abs(corr) / 1.0, 1.0)
            findings.append(CausalFinding(
                rule_id="TARGET_LEAKAGE",
                severity=CausalSeverity.WARNING,
                status=FindingStatus.SUSPECTED,
                detection_type=DetectionType.HEURISTIC,
                confidence=round(confidence, 4),
                message=f"Feature '{col}' has {corr:.3f} correlation with target "
                        f"'{target_column}' — suspected target leakage or "
                        f"post-outcome variable. Requires manual review.",
                column=col,
                evidence=CausalEvidence(
                    description=f"Pearson correlation between '{col}' and "
                                f"'{target_column}' is {corr:.4f}. Features with "
                                f"near-perfect target correlation may be post-outcome "
                                f"variables or trivial transformations of the target, "
                                f"but could also be legitimate derived features.",
                    columns_involved=[col, target_column],
                    statistic_name="pearson_correlation_with_target",
                    statistic_value=round(corr, 4),
                    threshold=correlation_threshold,
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# EXACT: Temporal ordering — features must precede target
# ---------------------------------------------------------------------------

def check_feature_timestamp_alignment(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    feature_timestamp_columns: Optional[Dict[str, str]] = None,
) -> List[CausalFinding]:
    """Check that feature timestamps do not come after the observation timestamp.

    Detection type: EXACT.
    If a feature's own timestamp is after the observation timestamp,
    the feature structurally uses future information. This is provable
    from the data alone — no statistical inference needed.
    """
    findings: List[CausalFinding] = []
    if not feature_timestamp_columns or timestamp_column not in df.columns:
        return findings

    work = df.copy()
    work["__primary_ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)

    for feature_col, feature_ts_col in feature_timestamp_columns.items():
        if feature_ts_col not in work.columns:
            continue
        work["__feat_ts"] = pd.to_datetime(work[feature_ts_col], errors="coerce", utc=True)
        violations = work["__feat_ts"] > work["__primary_ts"]
        violations = violations.fillna(False)
        violation_count = int(violations.sum())

        if violation_count > 0:
            bad_indices = work.index[violations].tolist()[:20]
            findings.append(CausalFinding(
                rule_id="FEATURE_TIMESTAMP_FUTURE",
                severity=CausalSeverity.UNSAFE,
                status=FindingStatus.DETECTED,
                detection_type=DetectionType.EXACT,
                confidence=1.0,
                message=f"Feature '{feature_col}' has {violation_count} rows where its "
                        f"timestamp ({feature_ts_col}) is AFTER the observation timestamp. "
                        f"This is a structural temporal violation.",
                column=feature_col,
                evidence=CausalEvidence(
                    description=f"{violation_count} rows have '{feature_ts_col}' > "
                                f"'{timestamp_column}'. This is structurally provable — "
                                f"the feature uses information from the future.",
                    columns_involved=[feature_col, feature_ts_col, timestamp_column],
                    sample_rows=bad_indices,
                    additional={"violation_count": violation_count},
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# HEURISTIC: Look-ahead bias suspicion
# ---------------------------------------------------------------------------

def check_lookahead_bias(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    series_column: str = "series_id",
    target_column: str = "value",
    feature_columns: Optional[List[str]] = None,
) -> List[CausalFinding]:
    """Flag features that correlate more strongly with future than past target.

    Detection type: HEURISTIC.
    A feature that correlates more strongly with target(t+1) than target(t-1)
    may contain look-ahead bias (e.g., centered rolling windows), but this
    pattern can also arise from legitimate autoregressive structure.
    """
    findings: List[CausalFinding] = []
    if timestamp_column not in df.columns or target_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"]).sort_values("__ts")

    if len(work) < 5:
        return findings

    work["__past_target"] = work[target_column].shift(1)
    work["__future_target"] = work[target_column].shift(-1)
    work = work.dropna(subset=["__past_target", "__future_target"])

    if feature_columns is None:
        feature_columns = [
            c for c in df.columns
            if c not in (timestamp_column, target_column, series_column)
            and pd.api.types.is_numeric_dtype(df[c])
        ]

    for col in feature_columns:
        if col not in work.columns or not pd.api.types.is_numeric_dtype(work[col]):
            continue
        valid = work[[col, "__past_target", "__future_target"]].dropna()
        if len(valid) < 5:
            continue
        if valid[col].std() == 0:
            continue

        corr_past = valid[col].corr(valid["__past_target"])
        corr_future = valid[col].corr(valid["__future_target"])

        if pd.isna(corr_past) or pd.isna(corr_future):
            continue

        gap = abs(corr_future) - abs(corr_past)
        if gap > 0.2 and abs(corr_future) > 0.5:
            # Confidence based on how much stronger the future correlation is
            confidence = min(gap / 1.0, 1.0)
            findings.append(CausalFinding(
                rule_id="LOOKAHEAD_BIAS",
                severity=CausalSeverity.WARNING,
                status=FindingStatus.SUSPECTED,
                detection_type=DetectionType.HEURISTIC,
                confidence=round(confidence, 4),
                message=f"Feature '{col}' correlates more with future target "
                        f"({corr_future:.3f}) than past target ({corr_past:.3f}) — "
                        f"suspected look-ahead bias. This could also arise from "
                        f"legitimate autoregressive structure.",
                column=col,
                evidence=CausalEvidence(
                    description=f"'{col}' correlation with target(t-1)={corr_past:.4f}, "
                                f"correlation with target(t+1)={corr_future:.4f}. "
                                f"The future correlation is stronger by {gap:.4f}. "
                                f"This pattern is consistent with centered or "
                                f"forward-looking window features but is not proof.",
                    columns_involved=[col, target_column],
                    statistic_name="future_vs_past_correlation_gap",
                    statistic_value=round(gap, 4),
                    additional={
                        "corr_with_past_target": round(corr_past, 4),
                        "corr_with_future_target": round(corr_future, 4),
                    },
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# EXACT: Train/test temporal contamination
# ---------------------------------------------------------------------------

def check_train_test_temporal_contamination(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    partition_column: Optional[str] = None,
    train_value: str = "train",
    test_value: str = "test",
    series_column: str = "series_id",
) -> List[CausalFinding]:
    """Check that no training data comes temporally after test data.

    Detection type: EXACT.
    Given an explicit partition column, verify that ALL training observations
    precede ALL test observations. If they overlap, the contamination is
    structurally provable from timestamps alone.
    """
    findings: List[CausalFinding] = []
    if partition_column is None or partition_column not in df.columns or timestamp_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"])

    train = work[work[partition_column] == train_value]
    test = work[work[partition_column] == test_value]

    if len(train) == 0 or len(test) == 0:
        findings.append(CausalFinding(
            rule_id="TEMPORAL_SPLIT_EMPTY",
            severity=CausalSeverity.WARNING,
            status=FindingStatus.DETECTED,
            detection_type=DetectionType.EXACT,
            confidence=1.0,
            message=f"Partition column '{partition_column}' produces an empty "
                    f"{'training' if len(train) == 0 else 'test'} set.",
            evidence=CausalEvidence(
                description=f"Partition check on '{partition_column}': {len(train)} train rows, "
                            f"{len(test)} test rows. One partition is empty.",
                additional={"train_count": len(train), "test_count": len(test)},
            ),
        ))
        return findings

    train_max = train["__ts"].max()
    test_min = test["__ts"].min()

    if train_max > test_min:
        overlap_count = int((train["__ts"] > test_min).sum())
        findings.append(CausalFinding(
            rule_id="TRAIN_TEST_TEMPORAL_OVERLAP",
            severity=CausalSeverity.CRITICAL,
            status=FindingStatus.DETECTED,
            detection_type=DetectionType.EXACT,
            confidence=1.0,
            message=f"Training data contains {overlap_count} rows with timestamps "
                    f"after the earliest test timestamp — structural temporal contamination.",
            evidence=CausalEvidence(
                description=f"Train max timestamp ({train_max}) > test min timestamp "
                            f"({test_min}). {overlap_count} training rows overlap "
                            f"with the test period. This is structurally provable.",
                statistic_name="temporal_overlap_count",
                statistic_value=float(overlap_count),
                additional={
                    "train_max_ts": str(train_max),
                    "test_min_ts": str(test_min),
                },
            ),
        ))

    # Per-series check if applicable
    if series_column in work.columns:
        contaminated_series = []
        for sid in work[series_column].unique()[:100]:
            s_train = train[train[series_column] == sid] if series_column in train.columns else pd.DataFrame()
            s_test = test[test[series_column] == sid] if series_column in test.columns else pd.DataFrame()
            if len(s_train) > 0 and len(s_test) > 0:
                if s_train["__ts"].max() > s_test["__ts"].min():
                    contaminated_series.append(str(sid))

        if contaminated_series:
            findings.append(CausalFinding(
                rule_id="SERIES_TEMPORAL_CONTAMINATION",
                severity=CausalSeverity.UNSAFE,
                status=FindingStatus.DETECTED,
                detection_type=DetectionType.EXACT,
                confidence=1.0,
                message=f"{len(contaminated_series)} series have training data "
                        f"temporally overlapping with test data.",
                evidence=CausalEvidence(
                    description=f"Within individual series, training timestamps "
                                f"overlap with test timestamps. This is per-series "
                                f"structural temporal contamination.",
                    additional={
                        "contaminated_series_count": len(contaminated_series),
                        "examples": contaminated_series[:10],
                    },
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# HEURISTIC: Suspicious post-outcome feature patterns
# ---------------------------------------------------------------------------

def check_post_outcome_features(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    target_column: str = "value",
    feature_columns: Optional[List[str]] = None,
) -> List[CausalFinding]:
    """Flag features that only become available after the target is observed.

    Detection type: HEURISTIC.
    A feature that is null for the first N% of the timeline and then
    becomes available could be a post-outcome variable, but could also
    be a feature that simply has a later start date.
    """
    findings: List[CausalFinding] = []
    if timestamp_column not in df.columns or target_column not in df.columns:
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    work = work.dropna(subset=["__ts"]).sort_values("__ts")

    if len(work) < 5:
        return findings

    if feature_columns is None:
        feature_columns = [
            c for c in df.columns
            if c not in (timestamp_column, target_column, "series_id")
        ]

    for col in feature_columns:
        if col not in work.columns:
            continue
        null_mask = work[col].isnull()
        if null_mask.sum() == 0 or null_mask.sum() == len(work):
            continue

        first_nonnull = null_mask.idxmin() if not null_mask.all() else None
        if first_nonnull is None:
            continue

        null_positions = work.index[null_mask].tolist()
        nonnull_positions = work.index[~null_mask].tolist()

        if len(null_positions) > 0 and len(nonnull_positions) > 0:
            if max(null_positions) < min(nonnull_positions):
                null_ratio = len(null_positions) / len(work)
                if null_ratio > 0.1:
                    confidence = min(null_ratio, 1.0)
                    findings.append(CausalFinding(
                        rule_id="POST_OUTCOME_FEATURE",
                        severity=CausalSeverity.WARNING,
                        status=FindingStatus.REQUIRES_REVIEW,
                        detection_type=DetectionType.HEURISTIC,
                        confidence=round(confidence, 4),
                        message=f"Feature '{col}' appears to become available only "
                                f"after the first {null_ratio:.0%} of the timeline — "
                                f"possible post-outcome variable. This could also "
                                f"be a feature with a later start date.",
                        column=col,
                        evidence=CausalEvidence(
                            description=f"'{col}' is null for the first "
                                        f"{len(null_positions)} rows ({null_ratio:.1%}), "
                                        f"then becomes available. This pattern is "
                                        f"consistent with a post-outcome variable but "
                                        f"is not proof — features with later collection "
                                        f"start dates exhibit the same pattern.",
                            columns_involved=[col],
                            statistic_name="delayed_availability_ratio",
                            statistic_value=round(null_ratio, 4),
                            additional={"null_count": len(null_positions)},
                        ),
                    ))
    return findings


# ---------------------------------------------------------------------------
# EXACT: Insufficient temporal structure
# ---------------------------------------------------------------------------

def check_temporal_structure_sufficiency(
    df: pd.DataFrame,
    timestamp_column: str = "timestamp",
    series_column: str = "series_id",
    min_observations_per_series: int = 10,
    min_series_count: int = 1,
) -> List[CausalFinding]:
    """Check that there is enough temporal structure for safety analysis.

    Detection type: EXACT.
    Whether the dataset has sufficient rows or series is structurally
    provable from a row count.
    """
    findings: List[CausalFinding] = []
    if timestamp_column not in df.columns:
        findings.append(CausalFinding(
            rule_id="NO_TEMPORAL_COLUMN",
            severity=CausalSeverity.WARNING,
            status=FindingStatus.DETECTED,
            detection_type=DetectionType.EXACT,
            confidence=1.0,
            message=f"No '{timestamp_column}' column found — "
                    f"cannot perform temporal safety analysis.",
            evidence=CausalEvidence(
                description=f"The dataset does not contain a '{timestamp_column}' "
                            f"column. Temporal safety cannot be assessed.",
                additional={"available_columns": list(df.columns)},
            ),
        ))
        return findings

    work = df.copy()
    work["__ts"] = pd.to_datetime(work[timestamp_column], errors="coerce", utc=True)
    valid = work.dropna(subset=["__ts"])

    if len(valid) < min_observations_per_series:
        findings.append(CausalFinding(
            rule_id="INSUFFICIENT_TEMPORAL_DEPTH",
            severity=CausalSeverity.WARNING,
            status=FindingStatus.DETECTED,
            detection_type=DetectionType.EXACT,
            confidence=1.0,
            message=f"Only {len(valid)} temporal observations — insufficient for "
                    f"reliable safety analysis (minimum: {min_observations_per_series}).",
            evidence=CausalEvidence(
                description=f"Dataset has {len(valid)} valid temporal rows. "
                            f"Safety analysis requires at least "
                            f"{min_observations_per_series} observations.",
                statistic_name="temporal_observation_count",
                statistic_value=float(len(valid)),
                threshold=float(min_observations_per_series),
            ),
        ))

    if series_column in df.columns:
        series_count = int(valid[series_column].nunique())
        if series_count < min_series_count:
            findings.append(CausalFinding(
                rule_id="INSUFFICIENT_SERIES_COUNT",
                severity=CausalSeverity.WARNING,
                status=FindingStatus.DETECTED,
                detection_type=DetectionType.EXACT,
                confidence=1.0,
                message=f"Only {series_count} series — insufficient for cross-series "
                        f"safety analysis (minimum: {min_series_count}).",
                evidence=CausalEvidence(
                    description=f"Dataset has {series_count} unique series. "
                                f"Cross-series temporal patterns require at least "
                                f"{min_series_count} series.",
                    statistic_name="series_count",
                    statistic_value=float(series_count),
                    threshold=float(min_series_count),
                ),
            ))
    return findings
