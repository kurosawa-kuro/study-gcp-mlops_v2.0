"""Ports for the ml/registry feature.

Phase C-2 introduced a Protocol layer above the existing Vertex AI Model
Registry façade so promotion / alias resolution can be driven by tests
or alternative backends (MLflow, Hugging Face Hub) without touching the
training pipeline.
"""

from .model_registry import ModelRegistryPort, RegisteredModelRef

__all__ = ["ModelRegistryPort", "RegisteredModelRef"]
