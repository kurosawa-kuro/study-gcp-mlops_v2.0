"""Training job: KFP reranker training pipeline definition + compile CLI.

Invoked by:

* ``python -m pipeline.training_job.main compile``  — KFP compile → YAML
* ``python -m pipeline.training_job.main submit``   — Vertex PipelineJob submit
"""

import argparse
from pathlib import Path
from typing import Any

from kfp import dsl

from pipeline.training_job.components import (
    evaluate_reranker,
    load_features,
    register_reranker,
    train_reranker,
)

PIPELINE_NAME = "property-search-train"


@dsl.pipeline(
    name=PIPELINE_NAME, description="Reranker training / evaluation / registration pipeline"
)
def property_search_train_pipeline(
    project_id: str = "mlops-dev-a",
    vertex_location: str = "asia-northeast1",
    feature_dataset_id: str = "feature_mart",
    feature_table: str = "property_features_daily",
    mlops_dataset_id: str = "mlops",
    ranking_log_table: str = "ranking_log",
    feedback_events_table: str = "feedback_events",
    window_days: int = 90,
    trainer_image: str = "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/property-trainer:latest",
    experiment_name: str = "property-reranker-lgbm",
    baseline_hyperparameters_json: str = '{"num_leaves":31,"learning_rate":0.05,"feature_fraction":0.9,"bagging_fraction":0.8,"min_data_in_leaf":50,"lambdarank_truncation_level":20}',
    gate_metric_name: str = "ndcg_at_10",
    gate_threshold: float = 0.6,
    model_display_name: str = "property-reranker",
    endpoint_resource_name: str = "",
    serving_container_image_uri: str = "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/property-reranker:latest",
    deploy_service_account: str = "",
    traffic_new_percentage: int = 10,
    deploy_machine_type: str = "n1-standard-2",
) -> None:
    features = load_features(
        project_id=project_id,
        feature_dataset_id=feature_dataset_id,
        feature_table=feature_table,
        mlops_dataset_id=mlops_dataset_id,
        ranking_log_table=ranking_log_table,
        feedback_events_table=feedback_events_table,
        window_days=window_days,
    )
    train_task = train_reranker(
        trainer_image=trainer_image,
        training_frame=features.outputs["training_frame"],
        hyperparameters_json=baseline_hyperparameters_json,
        experiment_name=experiment_name,
        window_days=window_days,
    )
    evaluate_task = evaluate_reranker(
        metrics_artifact=train_task.outputs["metrics"],
        metric_name=gate_metric_name,
        threshold=gate_threshold,
    )
    with dsl.Condition(evaluate_task.output == True):  # noqa: E712
        register_reranker(
            project_id=project_id,
            vertex_location=vertex_location,
            model_display_name=model_display_name,
            endpoint_resource_name=endpoint_resource_name,
            serving_container_image_uri=serving_container_image_uri,
            service_account=deploy_service_account,
            traffic_new_percentage=traffic_new_percentage,
            deploy_machine_type=deploy_machine_type,
            # KFP の Input[Artifact] 経由ではなく、train_reranker が string で
            # 返した model.uri を直接渡す。return 値は "Output" というデフォルト
            # 名の outputs 項目として参照する。
            model_artifact_uri=train_task.outputs["Output"],
        )


def build_pipeline_spec() -> dict[str, object]:
    return {
        "name": PIPELINE_NAME,
        "description": "Reranker training / evaluation / registration pipeline",
        "parameters": {
            "project_id": "mlops-dev-a",
            "vertex_location": "asia-northeast1",
            "feature_dataset_id": "feature_mart",
            "feature_table": "property_features_daily",
            "mlops_dataset_id": "mlops",
            "ranking_log_table": "ranking_log",
            "feedback_events_table": "feedback_events",
            "window_days": 90,
            "trainer_image": "asia-northeast1-docker.pkg.dev/mlops-dev-a/mlops/property-trainer:latest",
            "experiment_name": "property-reranker-lgbm",
            "gate_metric_name": "ndcg_at_10",
            "gate_threshold": 0.6,
            "model_display_name": "property-reranker",
        },
        "steps": [
            "load_features",
            "train_reranker",
            "evaluate",
            "register_reranker",
        ],
    }


def get_pipeline() -> Any:
    return property_search_train_pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="property-search-train pipeline CLI")
    parser.add_argument("action", choices=["compile", "submit"], default="compile", nargs="?")
    parser.add_argument("--output-dir", default="dist/pipelines")
    args = parser.parse_args(argv)

    from pipeline.workflow.compile import compile_pipeline, submit_pipeline_yaml

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    template = out / f"{PIPELINE_NAME}.yaml"
    compile_pipeline(get_pipeline(), template)
    if args.action == "submit":
        submit_pipeline_yaml(PIPELINE_NAME, template, build_pipeline_spec()["parameters"])  # type: ignore[arg-type]
    print(template)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
