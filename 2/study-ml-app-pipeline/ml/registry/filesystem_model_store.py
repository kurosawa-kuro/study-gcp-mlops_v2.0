"""Filesystem model-store adapter."""

from pathlib import Path

import lightgbm as lgb

from ml.evaluation.metrics import save_metrics
from ml.registry.port import ModelStore


class FilesystemModelStore(ModelStore):
    def __init__(self, model_dir: str) -> None:
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, booster: lgb.Booster, metrics: dict) -> str:
        run_dir = self.model_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        model_path = run_dir / "model.lgb"
        booster.save_model(str(model_path))
        payload = dict(metrics)
        payload["run_id"] = run_id
        save_metrics(payload, str(run_dir / "metrics.json"))
        self.set_latest(run_id)
        return str(model_path)

    def load(self, run_id: str) -> lgb.Booster:
        target_run = self.get_latest_run_id() if run_id == "latest" else run_id
        model_path = self.model_dir / target_run / "model.lgb"
        return lgb.Booster(model_file=str(model_path))

    def set_latest(self, run_id: str) -> None:
        latest = self.model_dir / "latest"
        latest_tmp = self.model_dir / f".latest_tmp_{run_id}"
        if latest_tmp.exists() or latest_tmp.is_symlink():
            latest_tmp.unlink()
        latest_tmp.symlink_to(run_id)
        latest_tmp.replace(latest)

    def get_latest_run_id(self) -> str:
        latest = self.model_dir / "latest"
        if latest.exists() and latest.is_symlink():
            return latest.readlink().as_posix()
        raise FileNotFoundError("latest symlink is missing")
