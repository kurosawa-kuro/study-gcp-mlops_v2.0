"""Phase 3 — ApiSettings (pydantic-settings driven).

Phase 7 の ``ApiSettings`` から GCP 系 (project_id / vertex_* / bq_* / kserve_*) を
全削除し、Local Docker Compose で動かすための最小集合に絞った版。

優先度 (高 → 低):
    1. 環境変数 (docker compose の `environment:` 経由で渡される)
    2. env/secret/credential.yaml (master key / postgres password)
    3. env/config/setting.yaml (非クレデンシャル設定)
    4. .env (ローカル override 用、.gitignore で覆う)
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

# app/settings.py → project root は parents[1]
_ROOT = Path(__file__).resolve().parents[1]
_SETTING_YAML = _ROOT / "env" / "config" / "setting.yaml"
_CREDENTIAL_YAML = _ROOT / "env" / "secret" / "credential.yaml"


class ApiSettings(BaseSettings):
    """Phase 3 search-api 用設定。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    enable_search: bool = True

    # --- 検索パラメータ ---
    top_k_default: int = 10
    rrf_k: int = 60
    candidate_pool_size: int = 100

    # --- Meilisearch ---
    meili_base_url: str = "http://meilisearch:7700"
    meili_index_name: str = "properties"
    # docker compose の environment: で渡される値。env から読む。
    meili_master_key: str = ""

    # --- PostgreSQL ---
    postgres_dsn: str = "postgresql://admin:password@postgres:5432/hybrid_search"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"
    redis_cache_ttl_seconds: int = 60

    # --- multilingual-e5 encoder ---
    e5_model_name: str = "intfloat/multilingual-e5-small"
    e5_embedding_dim: int = 384
    e5_max_seq_length: int = 512

    # --- LightGBM reranker ---
    model_artifacts_root: str = "ml/registry/artifacts"
    reranker_model_filename: str = "model.lgb"

    # --- Logging ---
    log_level: str = "INFO"

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
