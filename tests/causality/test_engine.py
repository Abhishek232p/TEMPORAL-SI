"""
Unit tests for the Temporal Safety Analysis Engine (Phase 010 — Hardened).

Tests validate:
1. Each rule category independently.
2. EXACT vs HEURISTIC classification.
3. Status (DETECTED/SUSPECTED/REQUIRES_REVIEW) correctness.
4. Confidence scores.
5. Verdict logic (only EXACT violations → CAUSAL_UNSAFE).
6. FALSE POSITIVE tests: legitimate features must NOT be classified as unsafe.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from packages.core.causality.engine import CausalSafetyEngine, CausalSafetyConfig
from packages.core.causality.findings import (
    CausalVerdict, CausalSeverity, DetectionType, FindingStatus,
)

@pytest.fixture
def engine():
    return CausalSafetyEngine()


# ---------------------------------------------------------------------------
# Test Data Generation Helpers
# ---------------------------------------------------------------------------

def generate_base_data(rows: int = 20) -> pd.DataFrame:
    """Generate basic temporal data with random walk target."""
    start_date = pd.to_datetime("2026-01-01T00:00:00Z")
    dates = [start_date + timedelta(days=i) for i in range(rows)]
    np.random.seed(42)
    target = np.cumsum(np.random.normal(0, 1, rows))
    df = pd.DataFrame({
        "timestamp": dates,
        "series_id": ["A"] * rows,
        "value": target,
        "feature_safe": np.random.normal(0, 1, rows)
    })
    return df


# ===========================================================================
# SECTION 1: EXACT RULE TESTS
# ===========================================================================

class TestTemporalSufficiency:
    """EXACT rule: row/series count checks."""

    def test_insufficient_depth(self, engine):
        df = generate_base_data(rows=5)
        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.INSUFFICIENT_EVIDENCE
        findings = [f for f in report.findings if f.rule_id == "INSUFFICIENT_TEMPORAL_DEPTH"]
        assert len(findings) == 1
        assert findings[0].detection_type == DetectionType.EXACT
        assert findings[0].status == FindingStatus.DETECTED
        assert findings[0].confidence == 1.0
        assert findings[0].evidence.statistic_value == 5.0
        assert findings[0].evidence.threshold == 10.0

    def test_missing_timestamp_column(self, engine):
        df = generate_base_data(rows=15).drop(columns=["timestamp"])
        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.INSUFFICIENT_EVIDENCE
        findings = [f for f in report.findings if f.rule_id == "NO_TEMPORAL_COLUMN"]
        assert len(findings) == 1
        assert findings[0].detection_type == DetectionType.EXACT
        assert findings[0].confidence == 1.0


class TestExactTemporalAlignment:
    """EXACT rule: feature timestamp > observation timestamp."""

    def test_feature_timestamp_future(self, engine):
        df = generate_base_data(rows=15)
        df["feat_ts"] = pd.to_datetime(df["timestamp"]) + timedelta(days=1)
        df["feature_x"] = np.random.normal(0, 1, 15)

        config = CausalSafetyConfig(feature_timestamp_columns={"feature_x": "feat_ts"})
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.CAUSAL_UNSAFE
        findings = [f for f in report.findings if f.rule_id == "FEATURE_TIMESTAMP_FUTURE"]
        assert len(findings) == 1
        assert findings[0].detection_type == DetectionType.EXACT
        assert findings[0].status == FindingStatus.DETECTED
        assert findings[0].confidence == 1.0
        assert findings[0].evidence.additional["violation_count"] == 15


class TestExactTrainTestContamination:
    """EXACT rule: train/test temporal overlap."""

    def test_train_test_contamination(self, engine):
        df = generate_base_data(rows=20)
        df["partition"] = "train"
        df.loc[10:, "partition"] = "test"
        temp = df.loc[0, "timestamp"]
        df.loc[0, "timestamp"] = df.loc[19, "timestamp"]
        df.loc[19, "timestamp"] = temp

        config = CausalSafetyConfig(partition_column="partition")
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.CAUSAL_UNSAFE
        contam = [f for f in report.findings if f.rule_id == "TRAIN_TEST_TEMPORAL_OVERLAP"]
        assert len(contam) == 1
        assert contam[0].detection_type == DetectionType.EXACT
        assert contam[0].status == FindingStatus.DETECTED
        assert contam[0].severity == CausalSeverity.CRITICAL
        assert contam[0].confidence == 1.0


# ===========================================================================
# SECTION 2: HEURISTIC RULE TESTS
# ===========================================================================

class TestHeuristicFutureLeakage:
    """HEURISTIC rule: future value correlation suspicion."""

    def test_future_value_leakage_suspected(self, engine):
        df = generate_base_data(rows=20)
        df["feature_future_leak"] = df["value"].shift(-1)

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        # HEURISTIC findings alone should NOT produce CAUSAL_UNSAFE
        assert report.verdict == CausalVerdict.SAFE_WITH_WARNINGS
        leak_findings = [f for f in report.findings if f.rule_id == "FUTURE_VALUE_LEAKAGE"]
        assert len(leak_findings) == 1
        assert leak_findings[0].detection_type == DetectionType.HEURISTIC
        assert leak_findings[0].status == FindingStatus.SUSPECTED
        assert leak_findings[0].confidence > 0.9
        assert leak_findings[0].column == "feature_future_leak"
        assert leak_findings[0].evidence.statistic_name == "pearson_correlation_with_future_target"

    def test_target_leakage_suspected(self, engine):
        df = generate_base_data(rows=20)
        df["feature_target_leak"] = df["value"] * 2

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        # HEURISTIC → SAFE_WITH_WARNINGS, not CAUSAL_UNSAFE
        assert report.verdict == CausalVerdict.SAFE_WITH_WARNINGS
        leak_findings = [f for f in report.findings if f.rule_id == "TARGET_LEAKAGE"]
        assert len(leak_findings) == 1
        assert leak_findings[0].detection_type == DetectionType.HEURISTIC
        assert leak_findings[0].status == FindingStatus.SUSPECTED
        assert leak_findings[0].column == "feature_target_leak"

    def test_lookahead_bias_suspected(self, engine):
        rows = 30
        start_date = pd.to_datetime("2026-01-01T00:00:00Z")
        dates = [start_date + timedelta(days=i) for i in range(rows)]
        np.random.seed(42)
        target = np.random.normal(0, 1, rows)
        df = pd.DataFrame({
            "timestamp": dates,
            "series_id": ["A"] * rows,
            "value": target,
        })
        df["feature_lookahead"] = df["value"].shift(-1) + np.random.normal(0, 0.1, rows)

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        bias_findings = [f for f in report.findings if f.rule_id == "LOOKAHEAD_BIAS"]
        assert len(bias_findings) >= 1
        assert bias_findings[0].detection_type == DetectionType.HEURISTIC
        assert bias_findings[0].status == FindingStatus.SUSPECTED
        assert bias_findings[0].column == "feature_lookahead"
        assert bias_findings[0].evidence.statistic_name == "future_vs_past_correlation_gap"


class TestHeuristicPostOutcome:
    """HEURISTIC rule: delayed feature availability."""

    def test_post_outcome_requires_review(self, engine):
        df = generate_base_data(rows=20)
        df["feature_post"] = np.random.normal(0, 1, 20)
        df.loc[0:4, "feature_post"] = np.nan

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        findings = [f for f in report.findings if f.rule_id == "POST_OUTCOME_FEATURE"]
        assert len(findings) == 1
        assert findings[0].detection_type == DetectionType.HEURISTIC
        assert findings[0].status == FindingStatus.REQUIRES_REVIEW
        assert findings[0].evidence.statistic_value == 0.25


# ===========================================================================
# SECTION 3: VERDICT LOGIC TESTS
# ===========================================================================

class TestVerdictLogic:
    """Test that verdict depends on EXACT vs HEURISTIC distinction."""

    def test_clean_data_produces_causal_safe(self, engine):
        df = generate_base_data(rows=20)
        df["feature_lag"] = df["value"].shift(1)
        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.CAUSAL_SAFE
        assert report.unsafe_count == 0
        assert report.critical_count == 0

    def test_heuristic_only_produces_safe_with_warnings_not_unsafe(self, engine):
        """Critical test: heuristic-only evidence must NOT produce CAUSAL_UNSAFE."""
        df = generate_base_data(rows=20)
        df["feature_suspicious"] = df["value"] * 2  # Target leakage (HEURISTIC)
        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.SAFE_WITH_WARNINGS
        assert report.verdict != CausalVerdict.CAUSAL_UNSAFE
        # Verify the finding IS heuristic
        for f in report.findings:
            if f.rule_id in ("TARGET_LEAKAGE", "FUTURE_VALUE_LEAKAGE"):
                assert f.detection_type == DetectionType.HEURISTIC

    def test_exact_violation_produces_causal_unsafe(self, engine):
        """EXACT structural violations must produce CAUSAL_UNSAFE."""
        df = generate_base_data(rows=15)
        df["feat_ts"] = pd.to_datetime(df["timestamp"]) + timedelta(days=1)
        df["feature_x"] = np.random.normal(0, 1, 15)

        config = CausalSafetyConfig(feature_timestamp_columns={"feature_x": "feat_ts"})
        report = engine.analyze(df, config)
        assert report.verdict == CausalVerdict.CAUSAL_UNSAFE

    def test_mixed_exact_and_heuristic_produces_unsafe(self, engine):
        """If both EXACT and HEURISTIC findings exist, EXACT wins → CAUSAL_UNSAFE."""
        df = generate_base_data(rows=15)
        df["feat_ts"] = pd.to_datetime(df["timestamp"]) + timedelta(days=1)
        df["feature_x"] = np.random.normal(0, 1, 15)
        df["feature_leak"] = df["value"] * 2  # heuristic too

        config = CausalSafetyConfig(feature_timestamp_columns={"feature_x": "feat_ts"})
        report = engine.analyze(df, config)
        assert report.verdict == CausalVerdict.CAUSAL_UNSAFE

    def test_report_is_deterministic(self, engine):
        df = generate_base_data(rows=20)
        config = CausalSafetyConfig()
        r1 = engine.analyze(df, config)
        r2 = engine.analyze(df, config)
        assert r1.to_dict() == r2.to_dict()


# ===========================================================================
# SECTION 4: FALSE POSITIVE TESTS
# These test that LEGITIMATE features are NOT classified as CAUSAL_UNSAFE.
# ===========================================================================

class TestFalsePositivePrevention:
    """Critical section: legitimate features must not be auto-classified as unsafe."""

    def test_legitimate_leading_indicator_not_unsafe(self, engine):
        """A genuine leading indicator correlates with future target but is
        available at prediction time. The engine should flag it as SUSPECTED
        at most, never CAUSAL_UNSAFE or DETECTED."""
        rows = 50
        np.random.seed(123)
        start_date = pd.to_datetime("2026-01-01T00:00:00Z")
        dates = [start_date + timedelta(days=i) for i in range(rows)]

        # Leading indicator: independent signal that naturally predicts
        # tomorrow's value through a causal mechanism
        leading_signal = np.random.normal(0, 1, rows)
        # Target is influenced by yesterday's leading signal + noise
        target = np.zeros(rows)
        for i in range(1, rows):
            target[i] = 0.95 * leading_signal[i-1] + np.random.normal(0, 0.1)

        df = pd.DataFrame({
            "timestamp": dates,
            "series_id": ["A"] * rows,
            "value": target,
            "leading_indicator": leading_signal,
        })

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        # The verdict must NOT be CAUSAL_UNSAFE
        assert report.verdict != CausalVerdict.CAUSAL_UNSAFE
        # If findings exist, they must be HEURISTIC/SUSPECTED
        for f in report.findings:
            if f.column == "leading_indicator":
                assert f.detection_type == DetectionType.HEURISTIC
                assert f.status != FindingStatus.DETECTED

    def test_proper_lagged_feature_not_flagged(self, engine):
        """A properly lagged feature (shift +1, i.e., yesterday's value)
        should not trigger any leakage warnings."""
        rows = 30
        start_date = pd.to_datetime("2026-01-01T00:00:00Z")
        dates = [start_date + timedelta(days=i) for i in range(rows)]
        np.random.seed(101)
        # Use white noise instead of random walk so autocorrelation is low
        target = np.random.normal(0, 1, rows)
        df = pd.DataFrame({
            "timestamp": dates,
            "series_id": ["A"] * rows,
            "value": target,
        })
        
        # This is a proper backward-looking feature
        df["feature_lag1"] = df["value"].shift(1)
        df["feature_lag2"] = df["value"].shift(2)

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.CAUSAL_SAFE
        leak_ids = {"FUTURE_VALUE_LEAKAGE", "TARGET_LEAKAGE", "LOOKAHEAD_BIAS"}
        for f in report.findings:
            if f.column in ("feature_lag1", "feature_lag2"):
                assert f.rule_id not in leak_ids

    def test_causal_rolling_feature_not_classified_unsafe(self, engine):
        """A backward-only rolling average (no centering) is legitimate.
        It should not produce CAUSAL_UNSAFE."""
        rows = 30
        df = generate_base_data(rows=rows)
        # Backward-only rolling mean: uses t, t-1, t-2
        df["feature_rolling_back"] = df["value"].rolling(window=3, center=False).mean()

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict != CausalVerdict.CAUSAL_UNSAFE
        # If any finding flags this feature, it must be HEURISTIC
        for f in report.findings:
            if f.column == "feature_rolling_back":
                assert f.detection_type == DetectionType.HEURISTIC

    def test_correlated_but_legitimate_feature_not_unsafe(self, engine):
        """A feature that is highly correlated with the target because of
        a shared underlying factor is NOT leakage. The engine should
        flag it as SUSPECTED at most."""
        rows = 30
        np.random.seed(42)
        start_date = pd.to_datetime("2026-01-01T00:00:00Z")
        dates = [start_date + timedelta(days=i) for i in range(rows)]

        # Both target and feature are driven by the same latent process
        latent = np.cumsum(np.random.normal(0, 1, rows))
        target = latent + np.random.normal(0, 0.3, rows)
        feature = latent + np.random.normal(0, 0.3, rows)

        df = pd.DataFrame({
            "timestamp": dates,
            "series_id": ["A"] * rows,
            "value": target,
            "feature_shared_latent": feature,
        })

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        # Must NOT be CAUSAL_UNSAFE
        assert report.verdict != CausalVerdict.CAUSAL_UNSAFE
        # If flagged, must be SUSPECTED not DETECTED
        for f in report.findings:
            if f.column == "feature_shared_latent":
                assert f.status == FindingStatus.SUSPECTED or f.status == FindingStatus.REQUIRES_REVIEW
                assert f.detection_type == DetectionType.HEURISTIC

    def test_independent_noise_feature_is_safe(self, engine):
        """A pure noise feature with no correlation to anything should
        produce CAUSAL_SAFE."""
        df = generate_base_data(rows=20)
        np.random.seed(99)
        df["noise_feature"] = np.random.normal(0, 1, 20)

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        assert report.verdict == CausalVerdict.CAUSAL_SAFE
        leak_ids = {"FUTURE_VALUE_LEAKAGE", "TARGET_LEAKAGE", "LOOKAHEAD_BIAS"}
        for f in report.findings:
            if f.column == "noise_feature":
                assert f.rule_id not in leak_ids

    def test_all_findings_have_evidence(self, engine):
        """Every finding in any report must carry a non-empty CausalEvidence."""
        df = generate_base_data(rows=20)
        df["feature_future_leak"] = df["value"].shift(-1)
        df["feature_target_leak"] = df["value"] * 2

        config = CausalSafetyConfig()
        report = engine.analyze(df, config)

        for f in report.findings:
            assert f.evidence is not None
            assert f.evidence.description is not None
            assert len(f.evidence.description) > 0
            assert f.detection_type in (DetectionType.EXACT, DetectionType.HEURISTIC)
            assert f.status in (
                FindingStatus.DETECTED,
                FindingStatus.SUSPECTED,
                FindingStatus.REQUIRES_REVIEW,
                FindingStatus.INSUFFICIENT_EVIDENCE,
            )
            assert 0.0 <= f.confidence <= 1.0

    def test_original_dataframe_not_mutated(self, engine):
        """The engine must never mutate the input DataFrame."""
        df = generate_base_data(rows=20)
        original_columns = list(df.columns)
        original_len = len(df)
        config = CausalSafetyConfig()
        engine.analyze(df, config)
        assert list(df.columns) == original_columns
        assert len(df) == original_len
