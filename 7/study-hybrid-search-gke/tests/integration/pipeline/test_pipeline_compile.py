from __future__ import annotations

from pipeline.workflow.compile import (
    _coerce_parameter_value,
    _merge_parameter_values,
    _spec,
)


def test_build_embed_pipeline_spec_contains_expected_steps() -> None:
    spec = _spec("embed")

    assert spec["name"] == "property-search-embed"
    assert spec["steps"] == ["load_properties", "batch_predict_embeddings", "write_embeddings"]


def test_build_train_pipeline_spec_contains_expected_steps() -> None:
    spec = _spec("train")

    assert spec["name"] == "property-search-train"
    assert spec["steps"] == [
        "load_features",
        "train_reranker",
        "evaluate",
        "register_reranker",
    ]


def test_coerce_parameter_value_handles_primitives_and_json() -> None:
    assert _coerce_parameter_value("true") is True
    assert _coerce_parameter_value("10") == 10
    assert _coerce_parameter_value("0.5") == 0.5
    assert _coerce_parameter_value('{"k": 1}') == {"k": 1}
    assert _coerce_parameter_value("asia-northeast1") == "asia-northeast1"


def test_merge_parameter_values_overrides_defaults() -> None:
    params = _merge_parameter_values(
        "train",
        ["window_days=30", 'baseline_hyperparameters_json={"num_leaves":63}'],
    )

    assert params["window_days"] == 30
    assert params["baseline_hyperparameters_json"] == {"num_leaves": 63}
