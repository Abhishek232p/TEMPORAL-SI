"""
Causal safety findings and report data structures.

These are entirely separate from Phase 009 quality findings.
Quality asks: "Is the data structurally sound?"
Causal safety asks: "Does this data exhibit temporal leakage risk
                      or structural safety violations?"

IMPORTANT EPISTEMOLOGICAL DISTINCTION:

This engine does NOT prove causality. It detects structural violations
(EXACT) and flags statistical suspicions (HEURISTIC). The distinction
between detection_type=EXACT and detection_type=HEURISTIC must be
preserved in all findings.

- EXACT: The violation is structurally provable from the data alone.
  Example: feature timestamp > observation timestamp.
  Example: training rows temporally overlap test rows.

- HEURISTIC: The finding is based on statistical evidence that is
  consistent with leakage but does not prove it.
  Example: high correlation with future target (could be a
  legitimate leading indicator).
  Example: feature highly correlated with target (could be a
  valid derived feature).

Every finding carries evidence — not just a boolean.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


class CausalVerdict(str, Enum):
    """Overall causal safety verdict."""
    CAUSAL_SAFE = "CAUSAL_SAFE"
    SAFE_WITH_WARNINGS = "SAFE_WITH_WARNINGS"
    CAUSAL_UNSAFE = "CAUSAL_UNSAFE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CausalSeverity(str, Enum):
    """Severity of a causal safety finding."""
    INFO = "INFO"
    WARNING = "WARNING"
    UNSAFE = "UNSAFE"
    CRITICAL = "CRITICAL"


class DetectionType(str, Enum):
    """Whether a finding is structurally provable or statistically inferred.

    EXACT:     The violation is provable from data structure alone.
               No statistical estimation is involved.
               False positives are impossible.

    HEURISTIC: The finding is based on statistical evidence that is
               consistent with a problem but does not prove it.
               False positives are possible.
               Legitimate features can trigger heuristic findings.
    """
    EXACT = "EXACT"
    HEURISTIC = "HEURISTIC"


class FindingStatus(str, Enum):
    """The certainty status of a finding.

    DETECTED:              Structurally proven (only valid for EXACT findings).
    SUSPECTED:             Statistical evidence suggests a problem.
    REQUIRES_REVIEW:       The evidence is ambiguous; human review needed.
    INSUFFICIENT_EVIDENCE: Not enough data to determine.
    """
    DETECTED = "DETECTED"
    SUSPECTED = "SUSPECTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class CausalEvidence:
    """Evidence supporting a causal safety finding.

    Every finding must carry evidence explaining why it was raised.
    This is not optional — a causal finding without evidence is useless.
    """
    description: str
    columns_involved: Optional[List[str]] = None
    sample_rows: Optional[List[int]] = None
    statistic_name: Optional[str] = None
    statistic_value: Optional[float] = None
    threshold: Optional[float] = None
    additional: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CausalFinding:
    """A single causal safety finding with mandatory evidence.

    Fields:
        rule_id:        Identifier for the rule that produced this finding.
        severity:       How serious the finding is (INFO → CRITICAL).
        status:         Certainty level (DETECTED, SUSPECTED, REQUIRES_REVIEW).
        detection_type: Whether the check is EXACT or HEURISTIC.
        confidence:     For HEURISTIC findings, a value in [0.0, 1.0]
                        indicating how strong the statistical signal is.
                        For EXACT findings, always 1.0.
        message:        Human-readable explanation.
        evidence:       Structured evidence supporting the finding.
        column:         Optional column name involved.
        details:        Optional additional details.
    """
    rule_id: str
    severity: str  # INFO, WARNING, UNSAFE, CRITICAL
    status: str  # DETECTED, SUSPECTED, REQUIRES_REVIEW, INSUFFICIENT_EVIDENCE
    detection_type: str  # EXACT, HEURISTIC
    confidence: float  # 0.0–1.0
    message: str
    evidence: CausalEvidence
    column: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "status": self.status,
            "detection_type": self.detection_type,
            "confidence": self.confidence,
            "message": self.message,
            "evidence": self.evidence.to_dict(),
            "column": self.column,
            "details": self.details,
        }


@dataclass
class CausalSafetyReport:
    """Aggregated causal safety report for a dataset version.

    The verdict is one of:
    - CAUSAL_SAFE: No leakage risk or temporal contamination detected.
    - SAFE_WITH_WARNINGS: Heuristic concerns that should be reviewed.
      Does NOT mean proven unsafe.
    - CAUSAL_UNSAFE: Structural violation detected (EXACT finding), or
      overwhelming heuristic evidence of leakage.
    - INSUFFICIENT_EVIDENCE: Not enough temporal structure to determine safety.

    Note: CAUSAL_SAFE means "no detectable leakage risk", not "causally proven safe".
    """
    verdict: str
    total_findings: int = 0
    critical_count: int = 0
    unsafe_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    findings: List[CausalFinding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "total_findings": self.total_findings,
            "critical_count": self.critical_count,
            "unsafe_count": self.unsafe_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "findings": [f.to_dict() for f in self.findings],
        }
