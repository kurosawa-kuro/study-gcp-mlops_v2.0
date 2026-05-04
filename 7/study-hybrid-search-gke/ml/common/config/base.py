"""Base settings — env-var / YAML driven via pydantic-settings.

優先度 (高 → 低):
    1. 環境変数 (本番は GKE ConfigMap / Secret 経由で注入)
    2. env/secret/credential.yaml (ローカル開発用シークレット)
    3. env/config/setting.yaml (非クレデンシャル設定の single source of truth)
    4. .env (ローカル override 用、commit 禁止 → root .gitignore で覆う)
    5. field default
"""

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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    project_id: str = "mlops-dev-a"
    region: str = "asia-northeast1"
    bq_dataset_mlops: str = "mlops"
    bq_dataset_feature_mart: str = "feature_mart"
    bq_table_training_runs: str = "training_runs"
    gcs_models_bucket: str = "mlops-dev-a-models"

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
