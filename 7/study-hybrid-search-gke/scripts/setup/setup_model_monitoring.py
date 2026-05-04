"""Resolve model monitoring configuration for the reranker endpoint."""

from __future__ import annotations

import argparse
import json
from typing import Any

from scripts._common import env

FEATURES = [
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "ctr",
    "fav_rate",
    "inquiry_rate",
]


def build_monitoring_spec() -> dict[str, Any]:
    project_id = env("PROJECT_ID")
    dataset_id = env("DATAFORM_DEFAULT_DATASET", "feature_mart")
    alerts_topic = env(
        "MODEL_MONITORING_ALERTS_TOPIC",
        f"projects/{project_id}/topics/model-monitoring-alerts",
    )
    return {
        "project_id": env("PROJECT_ID"),
        "vertex_location": env("VERTEX_LOCATION", env("REGION")),
        "reranker_endpoint_name": env("VERTEX_RERANKER_ENDPOINT_ID"),
        "monitoring_topic": alerts_topic,
        "monitoring_table": env(
            "MODEL_MONITORING_ALERTS_TABLE",
            f"{project_id}.mlops.model_monitoring_alerts",
        ),
        "feature_dataset_uri": f"bq://{project_id}.{dataset_id}.property_features_daily",
        "prediction_dataset_uri": f"bq://{project_id}.mlops.ranking_log",
        "feature_drift_threshold": float(env("MODEL_MONITORING_FEATURE_THRESHOLD", "0.3")),
        "prediction_drift_threshold": float(env("MODEL_MONITORING_PREDICTION_THRESHOLD", "0.3")),
        "schedule_cron": env("MODEL_MONITORING_SCHEDULE_CRON", "0 20 * * *"),
        "feature_names": FEATURES,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Vertex model monitoring spec")
    parser.parse_args()
    print(json.dumps(build_monitoring_spec(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
