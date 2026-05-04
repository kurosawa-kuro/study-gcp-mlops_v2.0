"""KFP component: evaluate gating metric from a metrics artifact."""

from kfp import dsl


@dsl.component(base_image="python:3.12")
def evaluate_reranker(
    metrics_artifact: dsl.Input[dsl.Metrics],
    metric_name: str,
    threshold: float,
) -> bool:
    import sys
    import traceback

    def _log(msg: str) -> None:
        print(f"[evaluate_reranker] {msg}", flush=True)
        print(f"[evaluate_reranker] {msg}", file=sys.stderr, flush=True)

    _log("STEP 1 — component entry")
    _log(f"  metric_name={metric_name} threshold={threshold}")
    _log(f"  metrics_artifact.uri={metrics_artifact.uri}")
    _log(f"  metrics_artifact.path={metrics_artifact.path}")

    try:
        import json
        from pathlib import Path

        metrics_path = Path(metrics_artifact.path)
        if metrics_path.exists():
            _log(f"  metrics_path exists, size={metrics_path.stat().st_size}")
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        else:
            _log("  metrics_path does NOT exist — using empty payload")
            payload = {}
        _log(f"  payload={payload}")
        value = float(payload.get(metric_name, 0.0))
        passed = value >= threshold
        _log(f"STEP 2 — {metric_name}={value} >= {threshold} -> {passed}")
        return passed
    except Exception:
        _log("ERROR in evaluate_reranker")
        _log(traceback.format_exc())
        raise
