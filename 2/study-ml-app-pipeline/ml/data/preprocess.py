"""Preprocessing logic."""

import numpy as np
import pandas as pd

from common.logging import get_logger
from ml.data.schema import FEATURE_COLS, TARGET_COL

logger = get_logger(__name__)

CAP_COLS = ["Population", "AveOccup", "AveRooms", "AveBedrms"]
CAP_UPPER_PERCENTILE = 99
LOG_COLS = ["Population", "AveOccup"]


def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = _handle_missing(df)
    df = _cap_outliers(df)
    df = _log_transform(df)
    return df


def _handle_missing(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in FEATURE_COLS + [TARGET_COL] if c in df.columns]
    missing = df[cols].isnull().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        logger.warning("Missing values found:\n%s", missing.to_string())
        df[cols] = df[cols].fillna(df[cols].median())
    return df


def _cap_outliers(df: pd.DataFrame) -> pd.DataFrame:
    for col in CAP_COLS:
        if col not in df.columns:
            continue
        upper = np.percentile(df[col], CAP_UPPER_PERCENTILE)
        n_capped = int((df[col] > upper).sum())
        if n_capped > 0:
            df[col] = df[col].clip(upper=upper)
            logger.info("Capped %s: %d rows (upper=%.2f)", col, n_capped, upper)
    return df


def _log_transform(df: pd.DataFrame) -> pd.DataFrame:
    for col in LOG_COLS:
        if col not in df.columns:
            continue
        df[col] = np.log1p(df[col])
        logger.info("Log-transformed %s", col)
    return df


def preprocess_input(values: dict) -> dict:
    out = dict(values)
    for col in LOG_COLS:
        if col in out:
            out[col] = float(np.log1p(out[col]))
    return out
