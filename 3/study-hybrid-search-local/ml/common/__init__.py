"""Shared primitives (config / logging / utilities) for app and ml jobs."""

from .logging import get_logger
from .utils import generate_run_id

__all__ = ["generate_run_id", "get_logger"]
