"""Preprocess tests."""

import numpy as np

from ml.data.preprocess import preprocess, preprocess_input


class TestPreprocess:
    def test_preserves_shape(self, sample_df):
        result = preprocess(sample_df)
        assert result.shape == sample_df.shape

    def test_no_missing_after_preprocess(self, sample_df):
        df = sample_df.copy()
        df.iloc[0, 0] = np.nan
        result = preprocess(df)
        assert result.isnull().sum().sum() == 0

    def test_caps_outliers(self, sample_df):
        df = sample_df.copy()
        df.loc[df.index[0], "Population"] = 1e9
        result = preprocess(df)
        assert result["Population"].max() < 1e9

    def test_log_transform_applied(self, sample_df):
        result = preprocess(sample_df)
        assert result["Population"].max() < sample_df["Population"].max()


class TestPreprocessInput:
    def test_log_transforms_target_cols(self):
        values = {"Population": 322, "AveOccup": 2.5, "MedInc": 8.3}
        result = preprocess_input(values)
        assert result["Population"] == float(np.log1p(322))
        assert result["AveOccup"] == float(np.log1p(2.5))
        assert result["MedInc"] == 8.3
