"""Playwright E2E 用のライブサーバ fixture.

uvicorn をバックグラウンドスレッドで起動し、セッション単位で使い回す。
tests/conftest.py の sample_df は function-scope なのでここでは再利用せず、
session-scope でモデル seeding 用の小さなデータフレームを自前で作る。
"""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest
import uvicorn


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _UvicornThread(threading.Thread):
    def __init__(self, app, host: str, port: int) -> None:
        super().__init__(daemon=True)
        config = uvicorn.Config(
            app, host=host, port=port, log_level="warning", lifespan="on"
        )
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        self.server.run()


def _seed_model(model_dir: Path) -> None:
    """lifespan の warmup と /predict が成立するよう、最小モデルを 1 本保存する."""
    from ml.registry.filesystem_model_store import FilesystemModelStore
    from ml.data.feature_engineering import engineer_features
    from ml.data.preprocess import preprocess
    from ml.training.trainer import train

    rng = np.random.RandomState(0)
    n = 100
    df = pd.DataFrame(
        {
            "MedInc": rng.uniform(1, 10, n),
            "HouseAge": rng.uniform(1, 50, n),
            "AveRooms": rng.uniform(2, 10, n),
            "AveBedrms": rng.uniform(0.5, 3, n),
            "Population": rng.uniform(100, 5000, n),
            "AveOccup": rng.uniform(1, 6, n),
            "Latitude": rng.uniform(32, 42, n),
            "Longitude": rng.uniform(-124, -114, n),
            "Price": rng.uniform(0.5, 5, n),
        }
    )
    train_df = engineer_features(preprocess(df.iloc[:80]))
    test_df = engineer_features(preprocess(df.iloc[80:]))
    booster, metrics = train(train_df, test_df)
    FilesystemModelStore(str(model_dir)).save("e2e_run", booster, metrics)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory) -> str:
    """学習済みモデルを一時ディレクトリに置き、uvicorn をバックグラウンド起動."""
    model_dir = tmp_path_factory.mktemp("e2e_artifacts") / "artifacts"
    model_dir.mkdir(parents=True, exist_ok=True)
    _seed_model(model_dir)

    os.environ["MODEL_DIR"] = str(model_dir)
    os.environ["MODEL_PATH"] = str(model_dir / "latest" / "model.lgb")

    # MODEL_DIR を反映させるため、app をインポートするのは env 設定後
    from app.main import app

    host, port = "127.0.0.1", _find_free_port()
    thread = _UvicornThread(app, host, port)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        thread.server.should_exit = True
        raise RuntimeError("uvicorn did not become ready within 10s")

    yield base_url

    thread.server.should_exit = True
    thread.join(timeout=5)
    os.environ.pop("MODEL_DIR", None)
    os.environ.pop("MODEL_PATH", None)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, live_server):
    """pytest-playwright の page fixture が使う base_url を live_server に揃える."""
    return {**browser_context_args, "base_url": live_server}
