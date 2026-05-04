"""Label assignment rule for LambdaRank training.

Policy: for a (request_id, property_id) pair, the strongest observed action
wins. Rationale: a user who clicked *and* inquired is a stronger positive than
one who only clicked; storing both would double-count the same intent.

Gain values live in :mod:`ml.data.feature_engineering.schema`.
"""

from __future__ import annotations

from collections.abc import Iterable

from ml.data.feature_engineering.schema import LABEL_GAIN


def assign_label(actions: Iterable[str]) -> int:
    """Return the gain of the strongest action in ``actions`` (0 if empty)."""
    best = 0
    for a in actions:
        gain = LABEL_GAIN.get(a, 0)
        if gain > best:
            best = gain
    return best
