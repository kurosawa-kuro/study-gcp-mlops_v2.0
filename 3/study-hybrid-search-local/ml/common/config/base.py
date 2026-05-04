"""Phase 3 — Base settings (env-var / YAML driven via pydantic-settings).

Phase 7 から GCP 系 (project_id / region / bq_dataset_* / gcs_models_bucket) を
全削除した版。Phase 4 で BigQuery / GCS が登場したら元の Phase 7 版に近づける形で
fields を増やす想定。

優先度 (高 → 低):
    1. 環境変数
    2. env/secret/credential.yaml
    3. env/config/setting.yaml
    4. .env
    5. field default
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# ml/common/config/base.py → project root は parents[3]
_ROOT = Path(__file__).resolve().parents[3]
_SETTING_YAML = _ROOT / "env" / "config" / "setting.yaml"
_CREDENTIAL_YAML = _ROOT / "env" / "secret" / "credential.yaml"


class BaseAppSettings(BaseSettings):
    """Phase 3 共通設定。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_dsn: str = "postgresql://admin:password@postgres:5432/hybrid_search"
    model_artifacts_root: str = "ml/registry/artifacts"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=_CREDENTIAL_YAML),
            YamlConfigSettingsSource(settings_cls, yaml_file=_SETTING_YAML),
            dotenv_settings,
            file_secret_settings,
        )


class TrainSettings(BaseAppSettings):
    """Phase 3 LightGBM LambdaRank 学習用設定。

    Phase 7 の TrainSettings から GCS / Vertex / project_id 系を全削除し、
    PostgreSQL DSN とローカル artifact path のみに絞る。
    """

    # --- 学習データソース (PostgreSQL ranking_log + feature_mart) ---
    training_window_days: int = 30
    min_request_id_count: int = 5

    # --- LightGBM hyperparameters ---
    num_boost_round: int = 200
    learning_rate: float = 0.05
    num_leaves: int = 31
    early_stopping_rounds: int = 30

    # --- Evaluation ---
    eval_at_k: int = 10  # NDCG@10
