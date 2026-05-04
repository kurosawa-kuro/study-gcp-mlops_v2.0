"""Embedding-job settings (thin subset of BaseAppSettings)."""

from .base import BaseAppSettings


class EmbedSettings(BaseAppSettings):
    """Env-driven settings required by the embedding pipeline / encoder CPR.

    Intentionally thin — ME5 hyperparameters live on :class:`ml.serving.encoder.E5Encoder`
    and LightGBM knobs belong to :class:`ml.common.config.training.TrainSettings`.
    """
