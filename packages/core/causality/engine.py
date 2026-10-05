"""
Orchestration engine for Temporal Safety Analysis (Phase 010).

This engine does NOT prove causality. It performs:
- Structural temporal safety checks (EXACT — provable from data alone)
- Statistical leakage-risk heuristics (HEURISTIC — consistent with problems
  but not proof)

The verdict reflects the strongest evidence found:
- EXACT violations → CAUSAL_UNSAFE (structurally proven)
- HEURISTIC suspicions only → SAFE_WITH_WARNINGS (requires human review)
- No findings → CAUSAL_SAFE (no detectable risk, not "proven safe")
- Insufficient data → INSUFFICIENT_EVIDENCE
"""

import pandas as pd
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from packages.core.causality.findings import (
    CausalFinding,
    CausalSafetyReport,
    CausalVerdict,
    CausalSeverity,
    DetectionType,
)
from packages.core.causality.rules import (
    check_future_value_leakage,
    check_target_leakage,
    check_feature_timestamp_alignment,
    check_lookahead_bias,
    check_train_test_temporal_contamination,
    check_post_outcome_features,
    check_temporal_structure_sufficiency,
)


@dataclass
class CausalSafetyConfig:
    """Configuration for causal safety analysis."""
    timestamp_column: str = "timestamp"
    target_column: str = "value"
    series_column: str = "series_id"
    feature_columns: Optional[List[str]] = None
    feature_timestamp_columns: Optional[Dict[str, str]] = None
    partition_column: Optional[str] = None
    train_value: str = "train"
    test_value: str = "test"
    correlation_threshold: float = 0.95
    min_observations_per_series: int = 10
    min_series_count: int = 1


class CausalSafetyEngine:
    """Orchestrates temporal safety analysis.

    The verdict logic distinguishes between EXACT and HEURISTIC findings:

    - EXACT findings with UNSAFE/CRITICAL severity → CAUSAL_UNSAFE
      These are structurally provable violations.

    - HEURISTIC findings alone → SAFE_WITH_WARNINGS
      These are statistical suspicions that require human review.
      The engine does not automatically classify heuristic evidence
      as "unsafe" because legitimate features can trigger these rules.
    """

    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame, config: CausalSafetyConfig) -> CausalSafetyReport:
        """Run all causal safety rules and produce a report.

        Does not mutate the DataFrame.
        """
        all_findings: List[CausalFinding] = []

        # 1. Check for basic temporal structure sufficiency
        sufficiency_findings = check_temporal_structure_sufficiency(
            df,
            timestamp_column=config.timestamp_column,
            series_column=config.series_column,
            min_observations_per_series=config.min_observations_per_series,
            min_series_count=config.min_series_count,
        )
        all_findings.extend(sufficiency_findings)

        # If there's no temporal column, we can't run the other rules.
        if any(f.rule_id == "NO_TEMPORAL_COLUMN" for f in sufficiency_findings):
            return self._build_report(all_findings, insufficient=True)

        # 2. Check future information leakage (HEURISTIC)
        all_findings.extend(check_future_value_leakage(
            df,
            timestamp_column=config.timestamp_column,
            target_column=config.target_column,
            feature_columns=config.feature_columns,
            correlation_threshold=config.correlation_threshold,
        ))

        # 3. Check target leakage (HEURISTIC)
        all_findings.extend(check_target_leakage(
            df,
            target_column=config.target_column,
            feature_columns=config.feature_columns,
            correlation_threshold=config.correlation_threshold,
            timestamp_column=config.timestamp_column,
        ))

        # 4. Check feature timestamp alignment (EXACT)
        all_findings.extend(check_feature_timestamp_alignment(
            df,
            timestamp_column=config.timestamp_column,
            feature_timestamp_columns=config.feature_timestamp_columns,
        ))

        # 5. Check lookahead bias (HEURISTIC)
        all_findings.extend(check_lookahead_bias(
            df,
            timestamp_column=config.timestamp_column,
            series_column=config.series_column,
            target_column=config.target_column,
            feature_columns=config.feature_columns,
        ))

        # 6. Check train/test temporal contamination (EXACT, if partition provided)
        if config.partition_column:
            all_findings.extend(check_train_test_temporal_contamination(
                df,
                timestamp_column=config.timestamp_column,
                partition_column=config.partition_column,
                train_value=config.train_value,
                test_value=config.test_value,
                series_column=config.series_column,
            ))

        # 7. Check post-outcome features (HEURISTIC)
        all_findings.extend(check_post_outcome_features(
            df,
            timestamp_column=config.timestamp_column,
            target_column=config.target_column,
            feature_columns=config.feature_columns,
        ))

        return self._build_report(all_findings)

    def _build_report(self, findings: List[CausalFinding], insufficient: bool = False) -> CausalSafetyReport:
        """Aggregate findings and determine the final verdict.

        Verdict logic:
        1. INSUFFICIENT_EVIDENCE — not enough data to analyze.
        2. CAUSAL_UNSAFE — at least one EXACT finding with UNSAFE or CRITICAL severity.
           Only structural violations can produce this verdict.
        3. SAFE_WITH_WARNINGS — heuristic suspicions exist but no structural proof.
           Requires human review.
        4. CAUSAL_SAFE — no detectable leakage risk.
        """
        critical = sum(1 for f in findings if f.severity == CausalSeverity.CRITICAL)
        unsafe = sum(1 for f in findings if f.severity == CausalSeverity.UNSAFE)
        warning = sum(1 for f in findings if f.severity == CausalSeverity.WARNING)
        info = sum(1 for f in findings if f.severity == CausalSeverity.INFO)

        if insufficient or any(f.rule_id == "INSUFFICIENT_TEMPORAL_DEPTH" for f in findings):
            verdict = CausalVerdict.INSUFFICIENT_EVIDENCE
        elif self._has_exact_violation(findings):
            # Only EXACT findings with UNSAFE/CRITICAL severity produce CAUSAL_UNSAFE
            verdict = CausalVerdict.CAUSAL_UNSAFE
        elif critical > 0 or unsafe > 0 or warning > 0:
            # Heuristic findings alone → SAFE_WITH_WARNINGS
            verdict = CausalVerdict.SAFE_WITH_WARNINGS
        else:
            verdict = CausalVerdict.CAUSAL_SAFE

        return CausalSafetyReport(
            verdict=verdict,
            total_findings=len(findings),
            critical_count=critical,
            unsafe_count=unsafe,
            warning_count=warning,
            info_count=info,
            findings=findings,
        )

    def _has_exact_violation(self, findings: List[CausalFinding]) -> bool:
        """Check if any finding is an EXACT detection with UNSAFE or CRITICAL severity."""
        for f in findings:
            if f.detection_type == DetectionType.EXACT and f.severity in (
                CausalSeverity.UNSAFE, CausalSeverity.CRITICAL
            ):
                return True
        return False
