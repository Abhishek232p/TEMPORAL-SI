"""
Quality findings and report data structures.

A QualityFinding represents a single validation result.
A QualityReport aggregates findings into a verdict: PASS, WARN, or FAIL.

These are plain data classes, not ORM models. The validation engine
produces them; the API layer persists them into DataQualityReport.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum


class Severity(str, Enum):
    """Severity levels for quality findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Verdict(str, Enum):
    """Overall quality verdict for a dataset version."""
    PASS_ = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class MeasurementType(str, Enum):
    """Whether a measurement is exact or estimated/sampled."""
    EXACT = "EXACT"
    SAMPLED = "SAMPLED"


@dataclass
class QualityFinding:
    """A single validation finding with location context."""
    rule_id: str
    severity: str  # INFO, WARNING, ERROR, CRITICAL
    message: str
    column: Optional[str] = None
    row_indices: Optional[List[int]] = None
    measurement_type: str = "EXACT"  # EXACT or SAMPLED
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QualityReport:
    """Aggregated quality report for a dataset version."""
    verdict: str  # PASS, WARN, FAIL
    total_findings: int = 0
    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    findings: List[QualityFinding] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "total_findings": self.total_findings,
            "critical_count": self.critical_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "findings": [f.to_dict() for f in self.findings],
        }
