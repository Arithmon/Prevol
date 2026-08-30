"""prevol — audit the declarations that a computational result carries.

A result should not travel alone. It should travel with the conditions under which it was produced and
with the means to check what one is entitled to conclude from it. This package audits whether those
declarations are still true — a question re-running the computation cannot answer, because re-running
produces a fresh document rather than auditing the one already published.
"""
from .coverage import (  # noqa: F401
    audit_source, check_coverage, check_vacuity, covers, read_structure,
)
from .core import (  # noqa: F401
    BLOCKING, REPORT, UNREADABLE,
    check_counter_coherence, check_freshness, check_mutation_probe,
    check_partial_run_discipline, check_provenance, declared_pins, read_boolean_table, self_check, severity_counts, verdict,
)

__version__ = "0.5.0"
__all__ = [
    "BLOCKING", "REPORT", "UNREADABLE", "check_counter_coherence", "check_freshness", "check_mutation_probe",
    "check_partial_run_discipline", "check_provenance", "declared_pins", "read_boolean_table",
    "self_check", "severity_counts", "verdict",
    "audit_source", "check_coverage", "check_vacuity", "covers", "read_structure",
    "__version__",
]
