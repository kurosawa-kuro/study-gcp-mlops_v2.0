"""Shared settings loader for phase 2."""

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

_ROOT = Path(__file__).resolve().parents[1]
_SETTING_YAML = _ROOT / "env" / "config" / "setting.yaml"
_CREDENTIAL_YAML = _ROOT / "env" / "secret" / "credential.yaml"


class BaseAppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

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
            file_secret_settings,
        )
