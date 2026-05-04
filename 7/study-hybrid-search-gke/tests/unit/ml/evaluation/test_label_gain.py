"""LambdaRank label assignment — strongest action wins."""

from ml.evaluation.metrics import assign_label


def test_inquiry_beats_favorite_beats_click() -> None:
    assert assign_label(["click", "favorite", "inquiry"]) == 3
    assert assign_label(["click", "favorite"]) == 2
    assert assign_label(["click"]) == 1


def test_empty_or_unknown_returns_zero() -> None:
    assert assign_label([]) == 0
    assert assign_label(["view"]) == 0  # not in LABEL_GAIN
