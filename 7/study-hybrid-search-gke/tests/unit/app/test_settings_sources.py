from __future__ import annotations

from pathlib import Path

from app.settings import ApiSettings
from ml.common.config import base as base_config


def test_apisettings_loads_non_secret_values_from_setting_yaml(monkeypatch, tmp_path: Path) -> None:
    # `make check` exports PROJECT_ID via Makefile L44; env wins over yaml in
    # pydantic-settings precedence (base.py L45-52). Strip the relevant fields
    # so this test exercises the yaml source in isolation.
    for var in (
        "PROJECT_ID",
        "MEILI_BASE_URL",
        "MEILI_IMPERSONATE_SERVICE_ACCOUNT",
        "MEILI_MASTER_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    setting_path = tmp_path / "setting.yaml"
    credential_path = tmp_path / "credential.yaml"
    setting_path.write_text(
        "\n".join(
            [
                'project_id: "custom-project"',
                'meili_base_url: "https://meili.example.com"',
                'meili_impersonate_service_account: "sa-api@custom-project.iam.gserviceaccount.com"',
            ]
        ),
        encoding="utf-8",
    )
    credential_path.write_text("meili_master_key: local-key\n", encoding="utf-8")
    monkeypatch.setattr(base_config, "_SETTING_YAML", setting_path)
    monkeypatch.setattr(base_config, "_CREDENTIAL_YAML", credential_path)

    settings = ApiSettings()

    assert settings.project_id == "custom-project"
    assert settings.meili_base_url == "https://meili.example.com"
    assert settings.meili_impersonate_service_account == (
        "sa-api@custom-project.iam.gserviceaccount.com"
    )
    assert settings.meili_master_key.get_secret_value() == "local-key"


def test_env_vars_override_yaml_sources(monkeypatch, tmp_path: Path) -> None:
    setting_path = tmp_path / "setting.yaml"
    credential_path = tmp_path / "credential.yaml"
    setting_path.write_text('project_id: "from-setting"\n', encoding="utf-8")
    credential_path.write_text('meili_master_key: "from-credential"\n', encoding="utf-8")
    monkeypatch.setattr(base_config, "_SETTING_YAML", setting_path)
    monkeypatch.setattr(base_config, "_CREDENTIAL_YAML", credential_path)
    monkeypatch.setenv("PROJECT_ID", "from-env")
    monkeypatch.setenv("MEILI_MASTER_KEY", "env-key")

    settings = ApiSettings()

    assert settings.project_id == "from-env"
    assert settings.meili_master_key.get_secret_value() == "env-key"
