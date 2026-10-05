"""
Unit tests for the Data Quality Validation Engine (Phase 009).

Tests validate each rule category independently and the engine's
verdict logic. No database or API dependency.
"""

import pytest
import pandas as pd
import numpy as np
from packages.core.quality.engine import ValidationEngine, ValidationConfig
from packages.core.quality.findings import Severity, Verdict


@pytest.fixture
def engine():
    return ValidationEngine()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_missing_required_column(self, engine):
        df = pd.DataFrame({"timestamp": ["2026-01-01"], "value": [10.0]})
        config = ValidationConfig(required_columns=["timestamp", "series_id", "value"])
        report = engine.validate(df, config)
        rule_ids = [f.rule_id for f in report.findings]
        assert "SCHEMA_REQUIRED_COLUMN" in rule_ids
        missing = [f for f in report.findings if f.rule_id == "SCHEMA_REQUIRED_COLUMN"]
        assert missing[0].column == "series_id"
        assert report.verdict == Verdict.FAIL

    def test_all_required_columns_present(self, engine):
        df = pd.DataFrame({"timestamp": ["2026-01-01"], "series_id": ["A"], "value": [10.0]})
        config = ValidationConfig(required_columns=["timestamp", "series_id", "value"])
        report = engine.validate(df, config)
        schema_findings = [f for f in report.findings if f.rule_id == "SCHEMA_REQUIRED_COLUMN"]
        assert len(schema_findings) == 0

    def test_dtype_mismatch(self, engine):
        df = pd.DataFrame({"value": ["not_a_number", "also_not"]})
        config = ValidationConfig(expected_dtypes={"value": "numeric"})
        report = engine.validate(df, config)
        dtype_findings = [f for f in report.findings if f.rule_id == "SCHEMA_DTYPE_MISMATCH"]
        assert len(dtype_findings) == 1
        assert dtype_findings[0].severity == Severity.ERROR


# ---------------------------------------------------------------------------
# Null validation
# ---------------------------------------------------------------------------

class TestNullValidation:
    def test_null_limit_exceeded(self, engine):
        df = pd.DataFrame({"value": [None, None, 1.0, 2.0]})
        config = ValidationConfig(max_null_fraction=0.25, null_check_columns=["value"])
        report = engine.validate(df, config)
        null_findings = [f for f in report.findings if f.rule_id == "NULL_LIMIT_EXCEEDED"]
        assert len(null_findings) == 1
        assert null_findings[0].details["null_fraction"] == 0.5

    def test_null_within_limit(self, engine):
        df = pd.DataFrame({"value": [1.0, 2.0, 3.0, None]})
        config = ValidationConfig(max_null_fraction=0.5, null_check_columns=["value"])
        report = engine.validate(df, config)
        null_findings = [f for f in report.findings if f.rule_id == "NULL_LIMIT_EXCEEDED"]
        assert len(null_findings) == 0


# ---------------------------------------------------------------------------
# Duplicate validation
# ---------------------------------------------------------------------------

class TestDuplicateValidation:
    def test_duplicates_detected(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "series_id": ["A", "A", "A"],
            "value": [10.0, 10.0, 20.0],
        })
        config = ValidationConfig(max_duplicate_fraction=0.0)
        report = engine.validate(df, config)
        dup_findings = [f for f in report.findings if f.rule_id == "DUPLICATE_ROWS"]
        assert len(dup_findings) == 1
        assert dup_findings[0].details["duplicate_count"] == 1

    def test_no_duplicates(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02"],
            "series_id": ["A", "A"],
            "value": [10.0, 20.0],
        })
        config = ValidationConfig(max_duplicate_fraction=0.0)
        report = engine.validate(df, config)
        dup_findings = [f for f in report.findings if f.rule_id == "DUPLICATE_ROWS"]
        assert len(dup_findings) == 0


# ---------------------------------------------------------------------------
# Timestamp validation
# ---------------------------------------------------------------------------

class TestTimestampValidation:
    def test_unparseable_timestamp(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "NOT_A_DATE", "2026-01-03"],
            "series_id": ["A", "A", "A"],
            "value": [10.0, 20.0, 30.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        ts_findings = [f for f in report.findings if f.rule_id == "TIMESTAMP_UNPARSEABLE"]
        assert len(ts_findings) == 1
        assert ts_findings[0].details["unparseable_count"] == 1

    def test_timestamp_out_of_order(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-03", "2026-01-01", "2026-01-02"],
            "series_id": ["A", "A", "A"],
            "value": [30.0, 10.0, 20.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        order_findings = [f for f in report.findings if f.rule_id == "TIMESTAMP_NOT_ORDERED"]
        assert len(order_findings) == 1

    def test_ordered_timestamps_pass(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "series_id": ["A", "A", "A"],
            "value": [10.0, 20.0, 30.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        order_findings = [f for f in report.findings if f.rule_id == "TIMESTAMP_NOT_ORDERED"]
        assert len(order_findings) == 0


# ---------------------------------------------------------------------------
# Temporal gaps and frequency
# ---------------------------------------------------------------------------

class TestTemporalGaps:
    def test_gap_detected(self, engine):
        df = pd.DataFrame({
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-03T00:00:00Z",
                "2026-01-10T00:00:00Z",  # 7-day gap
            ],
            "series_id": ["A", "A", "A", "A"],
            "value": [1.0, 2.0, 3.0, 4.0],
        })
        config = ValidationConfig(gap_multiplier=2.0)
        report = engine.validate(df, config)
        gap_findings = [f for f in report.findings if f.rule_id == "TEMPORAL_GAPS"]
        assert len(gap_findings) == 1
        assert gap_findings[0].details["gap_count"] >= 1

    def test_irregular_frequency_reported(self, engine):
        df = pd.DataFrame({
            "timestamp": [
                "2026-01-01T00:00:00Z",
                "2026-01-02T00:00:00Z",
                "2026-01-04T00:00:00Z",  # irregular
            ],
            "series_id": ["A", "A", "A"],
            "value": [1.0, 2.0, 3.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        freq_findings = [f for f in report.findings if f.rule_id == "FREQUENCY_INCONSISTENT"]
        assert len(freq_findings) == 1
        assert freq_findings[0].measurement_type in ("EXACT", "SAMPLED")


# ---------------------------------------------------------------------------
# Series continuity
# ---------------------------------------------------------------------------

class TestSeriesContinuity:
    def test_short_series_flagged(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02", "2026-01-01"],
            "series_id": ["A", "A", "B"],
            "value": [10.0, 20.0, 5.0],
        })
        config = ValidationConfig(min_series_observations=2)
        report = engine.validate(df, config)
        short_findings = [f for f in report.findings if f.rule_id == "SERIES_TOO_SHORT"]
        assert len(short_findings) == 1
        assert short_findings[0].details["short_series_count"] == 1


# ---------------------------------------------------------------------------
# Numeric value validation
# ---------------------------------------------------------------------------

class TestNumericValues:
    def test_inf_values_detected(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02"],
            "series_id": ["A", "A"],
            "value": [10.0, float("inf")],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        inf_findings = [f for f in report.findings if f.rule_id == "NUMERIC_INF_VALUES"]
        assert len(inf_findings) == 1
        assert report.verdict == Verdict.FAIL

    def test_constant_series_detected(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "series_id": ["A", "A", "A"],
            "value": [5.0, 5.0, 5.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        const_findings = [f for f in report.findings if f.rule_id == "CONSTANT_SERIES"]
        assert len(const_findings) == 1


# ---------------------------------------------------------------------------
# Value bounds
# ---------------------------------------------------------------------------

class TestValueBounds:
    def test_out_of_bounds_detected(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02"],
            "series_id": ["A", "A"],
            "value": [-100.0, 500.0],
        })
        config = ValidationConfig(value_bounds={"value": {"min": 0.0, "max": 100.0}})
        report = engine.validate(df, config)
        bound_findings = [f for f in report.findings if f.rule_id == "VALUE_OUT_OF_BOUNDS"]
        assert len(bound_findings) == 1
        assert bound_findings[0].details["violation_count"] == 2


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------

class TestVerdictLogic:
    def test_clean_data_passes(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"],
            "series_id": ["A", "A", "A"],
            "value": [10.0, 20.0, 30.0],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        # Clean regular data should PASS (or WARN for frequency if only 3 points)
        assert report.verdict in (Verdict.PASS_, Verdict.WARN)
        assert report.critical_count == 0
        assert report.error_count == 0

    def test_error_findings_cause_fail(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01"],
            "series_id": ["A"],
            "value": [float("inf")],
        })
        config = ValidationConfig()
        report = engine.validate(df, config)
        assert report.verdict == Verdict.FAIL
        assert report.error_count >= 1

    def test_report_is_deterministic(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02", "2026-01-05"],
            "series_id": ["A", "A", "A"],
            "value": [1.0, 2.0, 3.0],
        })
        config = ValidationConfig()
        r1 = engine.validate(df, config)
        r2 = engine.validate(df, config)
        assert r1.to_dict() == r2.to_dict()

    def test_original_dataframe_not_mutated(self, engine):
        df = pd.DataFrame({
            "timestamp": ["2026-01-01", "2026-01-02"],
            "series_id": ["A", "A"],
            "value": [10.0, 20.0],
        })
        original_columns = list(df.columns)
        original_len = len(df)
        config = ValidationConfig()
        engine.validate(df, config)
        assert list(df.columns) == original_columns
        assert len(df) == original_len
