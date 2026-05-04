"""Filesystem model store tests."""

import lightgbm as lgb
import numpy as np

from ml.registry.filesystem_model_store import FilesystemModelStore


def _tiny_booster():
    x = np.array([[1.0], [2.0], [3.0], [4.0]])
    y = np.array([1.0, 1.5, 2.0, 2.5])
    ds = lgb.Dataset(x, label=y)
    return lgb.train({"objective": "regression", "verbosity": -1}, ds, num_boost_round=5)


def test_save_and_load(tmp_path):
    store = FilesystemModelStore(str(tmp_path / "artifacts"))
    booster = _tiny_booster()
    store.save("run_001", booster, {"rmse": 0.1, "r2": 0.9})
    loaded = store.load("latest")
    pred = loaded.predict(np.array([[2.0]]))[0]
    assert isinstance(float(pred), float)
