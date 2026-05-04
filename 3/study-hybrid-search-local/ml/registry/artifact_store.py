"""Phase 3 — LocalArtifactStore.

学習成果物 (LightGBM model / metrics.json / feature_importance.csv) をローカル
ファイルシステムに書き出す。Phase 7 の `GcsArtifactUploader` の Phase 3 版。

Phase 4 で GCS uploader と並行実装する想定 (本ファイルは Phase 3 でも残す)。
"""

from __future__ import annotations

from pathlib import Path


class LocalArtifactStore:
    """Phase 3 用ローカル artifact 出力。

    ``ml/registry/artifacts/{run_id}/{model.lgb,metrics.json,feature_importance.csv}``
    に書き出し、`latest` シンボリックリンクを最新 run に張り替える。
    """

    def __init__(self, *, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        target = self._root / run_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    def update_latest(self, run_id: str) -> Path:
        """`latest` シンボリックリンクを ``run_id`` ディレクトリに張り替える。"""
        latest_link = self._root / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(run_id, target_is_directory=True)
        return latest_link
