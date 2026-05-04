"""KFP component: materialize the training-frame query contract."""

from kfp import dsl


@dsl.component(base_image="python:3.12")
def load_features(
    project_id: str,
    feature_dataset_id: str,
    feature_table: str,
    mlops_dataset_id: str,
    ranking_log_table: str,
    feedback_events_table: str,
    window_days: int,
    training_frame: dsl.Output[dsl.Dataset],
) -> None:
    import sys
    import traceback

    def _log(msg: str) -> None:
        print(f"[load_features] {msg}", flush=True)
        print(f"[load_features] {msg}", file=sys.stderr, flush=True)

    _log("STEP 1 — component entry")
    _log(f"  project_id={project_id}")
    _log(f"  feature_dataset_id={feature_dataset_id} feature_table={feature_table}")
    _log(f"  mlops_dataset_id={mlops_dataset_id} ranking_log_table={ranking_log_table}")
    _log(f"  feedback_events_table={feedback_events_table} window_days={window_days}")
    _log(f"  training_frame.uri={training_frame.uri} path={training_frame.path}")

    try:
        import json
        from pathlib import Path

        query = f"""
        SELECT
          r.request_id,
          r.property_id,
          r.features.rent,
          r.features.walk_min,
          r.features.age_years,
          r.features.area_m2,
          r.features.ctr,
          r.features.fav_rate,
          r.features.inquiry_rate,
          r.features.me5_score,
          r.features.lexical_rank,
          COALESCE(l.label, 0) AS label
        FROM `{project_id}.{mlops_dataset_id}.{ranking_log_table}` r
        LEFT JOIN `{project_id}.{mlops_dataset_id}.{feedback_events_table}` l
          USING (request_id, property_id)
        JOIN `{project_id}.{feature_dataset_id}.{feature_table}` f
          USING (property_id)
        WHERE r.ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {window_days} DAY)
        ORDER BY r.request_id, r.features.lexical_rank
        """.strip()

        _log("STEP 2 — build payload (no BigQuery call; this is a contract stub)")
        payload = {
            "component": "load_features",
            "project_id": project_id,
            "feature_dataset_id": feature_dataset_id,
            "feature_table": feature_table,
            "mlops_dataset_id": mlops_dataset_id,
            "ranking_log_table": ranking_log_table,
            "feedback_events_table": feedback_events_table,
            "window_days": window_days,
            "split_strategy": "FARM_FINGERPRINT(request_id) % 10 < 8",
            "query": query,
        }
        training_frame.metadata.update(payload)
        _log(f"STEP 3 — write stub to {training_frame.path}")
        Path(training_frame.path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _log(f"  wrote {Path(training_frame.path).stat().st_size} bytes")
        _log("DONE")
    except Exception:
        _log("ERROR in load_features")
        _log(traceback.format_exc())
        raise
