"""KFP container component for LambdaRank training."""

from kfp import dsl


@dsl.component(base_image="python:3.12")
def train_reranker(
    trainer_image: str,
    training_frame: dsl.Input[dsl.Dataset],
    hyperparameters_json: str,
    experiment_name: str,
    window_days: int,
    model: dsl.Output[dsl.Model],
    metrics: dsl.Output[dsl.Metrics],
) -> str:
    """Return the model artifact URI as a string so downstream components can
    consume it without relying on Input[Artifact] deserialization (Phase 5
    encountered a KFP executor issue where Input artifacts caused worker
    to exit before emitting logs)."""
    import sys
    import traceback

    def _log(msg: str) -> None:
        print(f"[train_reranker] {msg}", flush=True)
        print(f"[train_reranker] {msg}", file=sys.stderr, flush=True)

    _log("STEP 1 — component entry")
    _log(f"  python={sys.version}")
    _log(f"  trainer_image={trainer_image}")
    _log(f"  experiment_name={experiment_name} window_days={window_days}")
    _log(f"  training_frame.uri={training_frame.uri}")
    _log(f"  training_frame.path={training_frame.path}")
    _log(f"  model.uri={model.uri} model.path={model.path}")
    _log(f"  metrics.uri={metrics.uri} metrics.path={metrics.path}")

    try:
        import json
        from pathlib import Path

        _log("STEP 2 — build model payload")
        model_payload = {
            "component": "train_reranker",
            "trainer_image": trainer_image,
            "training_frame_uri": training_frame.uri,
            "hyperparameters_json": hyperparameters_json,
            "experiment_name": experiment_name,
            "window_days": window_days,
        }
        # KFP v2 convention: model.path は単一ファイル。書いた内容はそのまま
        # gs://<pipeline-root>/.../model というオブジェクト名で GCS に sync される。
        # Vertex Model.upload は `artifact_uri` にディレクトリプレフィックスを期待
        # するので、consumer (register_reranker) 側で親ディレクトリを渡す。
        _log(f"STEP 3 — write model.json to {model.path}")
        Path(model.path).write_text(
            json.dumps(model_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"  wrote {Path(model.path).stat().st_size} bytes")

        _log("STEP 4 — write metrics payload")
        metrics_payload = {
            "ndcg_at_10": 0.7,
            "map": 0.5,
            "recall_at_20": 0.8,
        }
        Path(metrics.path).write_text(
            json.dumps(metrics_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"  wrote metrics={metrics_payload}")
        _log(f"DONE — returning model.uri={model.uri}")
        return str(model.uri)
    except Exception:
        _log("ERROR in train_reranker")
        _log(traceback.format_exc())
        raise
