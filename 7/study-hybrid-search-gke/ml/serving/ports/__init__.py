"""Ports for the ml/serving feature (client-side).

The KServe **server-side** entrypoints (``ml/serving/encoder.py`` /
``ml/serving/reranker.py``) stay as concrete FastAPI apps — they are
container entrypoints, not abstract services. The Port layer here covers
the **client-side** of model invocation (used by app/services and by
batch_serving_job).
"""

from .predictor_service import PredictorService

__all__ = ["PredictorService"]
