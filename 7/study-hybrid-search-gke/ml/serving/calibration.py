"""Score calibration (Platt / isotonic) — future hook.

Placeholder for serve-time calibration between raw LightGBM scores and
production-facing relevance scores. Not implemented yet.
"""

from __future__ import annotations


def identity_calibrator(score: float) -> float:
    """Pass-through calibrator used as a no-op default."""
    return score
