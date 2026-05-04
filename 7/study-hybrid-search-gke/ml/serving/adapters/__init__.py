"""Adapters implementing ``ml/serving/ports``."""

from .kserve_predictor import KServePredictorAdapter

__all__ = ["KServePredictorAdapter"]
