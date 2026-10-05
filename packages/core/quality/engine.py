"""
Data Quality Validation Engine.

Orchestrates quality rules against a DataFrame and produces a QualityReport.

The engine:
- Reads a DataProfile (Phase 008 output) for context.
- Runs deterministic validation rules against actual data.
- Never mutates the input DataFrame or the DatasetVersion.
- Classifies the overall verdict as PASS / WARN / FAIL.
- Does NOT compute an arbitrary numeric score.
"""

import pandas as pd
from typing import List, Dict, Any, Optional

from packages.core.quality.findings import (
    QualityFinding,
    QualityReport,
    Severity,
    Verdict,
)
from packages.core.quality import rules as R


class ValidationConfig:
    """Configuration for a validation run.

    All fields are optional. The engine applies sensible defaults when
    a field is not provided.
    """

    def __init__(
        self,
        required_columns: Optional[List[str]] = None,
        expected_dtypes: Optional[Dict[str, str]] = None,
        max_null_fraction: float = 1.0,
        null_check_columns: Optional[List[str]] = None,
        max_duplicate_fraction: float = 0.0,
        timestamp_column: str = "timestamp",
        series_column: str = "series_id",
        value_column: str = "value",
        gap_multiplier: float = 2.0,
        min_series_observations: int = 2,
        value_bounds: Optional[Dict[str, Dict[str, float]]] = None,
        max_series_sample: int = 100,
    ):
        self.required_columns = required_columns or []
        self.expected_dtypes = expected_dtypes or {}
        self.max_null_fraction = max_null_fraction
        self.null_check_columns = null_check_columns
        self.max_duplicate_fraction = max_duplicate_fraction
        self.timestamp_column = timestamp_column
        self.series_column = series_column
        self.value_column = value_column
        self.gap_multiplier = gap_multiplier
        self.min_series_observations = min_series_observations
        self.value_bounds = value_bounds or {}
        self.max_series_sample = max_series_sample


class ValidationEngine:
    """Runs quality validation rules and produces a QualityReport."""

    def validate(
        self,
        df: pd.DataFrame,
        config: Optional[ValidationConfig] = None,
    ) -> QualityReport:
        """Run all applicable validation rules against the DataFrame.

        The DataFrame is never mutated. The config controls which rules
        are activated and their thresholds.
        """
        if config is None:
            config = ValidationConfig()

        # Use a defensive copy so rules cannot accidentally mutate the original
        df_copy = df.copy()

        all_findings: List[QualityFinding] = []

        # Schema validation
        if config.required_columns:
            all_findings.extend(
                R.validate_required_columns(df_copy, config.required_columns)
            )

        if config.expected_dtypes:
            all_findings.extend(
                R.validate_column_dtypes(df_copy, config.expected_dtypes)
            )

        # Null validation
        all_findings.extend(
            R.validate_null_limits(
                df_copy,
                max_null_fraction=config.max_null_fraction,
                columns=config.null_check_columns,
            )
        )

        # Duplicate validation
        all_findings.extend(
            R.validate_duplicates(df_copy, max_duplicate_fraction=config.max_duplicate_fraction)
        )

        # Timestamp validation
        all_findings.extend(
            R.validate_timestamp_parseable(df_copy, timestamp_column=config.timestamp_column)
        )
        all_findings.extend(
            R.validate_timestamp_ordering(
                df_copy,
                timestamp_column=config.timestamp_column,
                series_column=config.series_column,
            )
        )

        # Temporal gaps
        all_findings.extend(
            R.validate_temporal_gaps(
                df_copy,
                timestamp_column=config.timestamp_column,
                series_column=config.series_column,
                gap_multiplier=config.gap_multiplier,
                max_series_sample=config.max_series_sample,
            )
        )

        # Frequency consistency
        all_findings.extend(
            R.validate_frequency_consistency(
                df_copy,
                timestamp_column=config.timestamp_column,
                series_column=config.series_column,
                max_series_sample=config.max_series_sample,
            )
        )

        # Series continuity
        all_findings.extend(
            R.validate_series_continuity(
                df_copy,
                series_column=config.series_column,
                min_observations=config.min_series_observations,
            )
        )

        # Numeric value validation
        all_findings.extend(
            R.validate_numeric_values(df_copy, value_column=config.value_column)
        )

        # Constant series detection
        all_findings.extend(
            R.validate_constant_series(
                df_copy,
                value_column=config.value_column,
                series_column=config.series_column,
            )
        )

        # Configurable value bounds
        if config.value_bounds:
            all_findings.extend(
                R.validate_value_bounds(df_copy, bounds=config.value_bounds)
            )

        # Build report
        return self._build_report(all_findings)

    def _build_report(self, findings: List[QualityFinding]) -> QualityReport:
        """Derive verdict from findings. No arbitrary scoring."""
        critical = sum(1 for f in findings if f.severity == Severity.CRITICAL)
        error = sum(1 for f in findings if f.severity == Severity.ERROR)
        warning = sum(1 for f in findings if f.severity == Severity.WARNING)
        info = sum(1 for f in findings if f.severity == Severity.INFO)

        # Verdict logic:
        # FAIL if any CRITICAL or ERROR findings exist.
        # WARN if only WARNING findings exist.
        # PASS otherwise.
        if critical > 0 or error > 0:
            verdict = Verdict.FAIL
        elif warning > 0:
            verdict = Verdict.WARN
        else:
            verdict = Verdict.PASS_

        return QualityReport(
            verdict=verdict,
            total_findings=len(findings),
            critical_count=critical,
            error_count=error,
            warning_count=warning,
            info_count=info,
            findings=findings,
        )
