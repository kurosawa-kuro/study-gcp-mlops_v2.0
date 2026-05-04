"""The Dataform repo root file `pipeline/data_job/dataform/workflow_settings.yaml` is not
committed — it is regenerated from `env/config/setting.yaml` by
`scripts/sync_dataform_config.py` (Makefile: `make sync-dataform-config`)
before any Dataform compile. CI runs the generator in both ci.yml and
deploy-dataform.yml.

This test verifies that the generator's `render()` output reflects the
current `setting.yaml` for every required Dataform key. If it fails, the
generator or setting.yaml is out of sync — not the workflow_settings.yaml
file (which is gitignored).
"""

from __future__ import annotations

from scripts.ci.sync_dataform import REQUIRED_KEYS, render
from tests.integration.parity.parity_invariant import REPO_ROOT, flat_yaml

SETTING_YAML = REPO_ROOT / "env" / "config" / "setting.yaml"


def test_generator_includes_every_required_dataform_key() -> None:
    rendered = flat_yaml(render())
    expected_keys = {
        "defaultProject",
        "defaultLocation",
        "defaultDataset",
        "defaultAssertionDataset",
        "dataformCoreVersion",
    }
    missing = expected_keys - rendered.keys()
    assert not missing, f"render() omitted Dataform keys: {missing}"


def test_generator_values_match_setting_yaml() -> None:
    setting = flat_yaml(SETTING_YAML.read_text(encoding="utf-8"))
    rendered = flat_yaml(render())

    expected = {
        "defaultProject": setting["project_id"],
        "defaultLocation": setting["region"],
        "defaultDataset": setting["dataform_default_dataset"],
        "defaultAssertionDataset": setting["dataform_default_assertion_dataset"],
        "dataformCoreVersion": setting["dataform_core_version"],
    }
    drift = {k: (rendered.get(k), v) for k, v in expected.items() if rendered.get(k) != v}
    assert not drift, (
        f"sync_dataform_config.render() drifted from setting.yaml: {drift}\n"
        "Fix scripts/sync_dataform_config.py or env/config/setting.yaml."
    )


def test_setting_yaml_has_all_required_keys() -> None:
    """Guard against silently dropping a Dataform-relevant key from setting.yaml."""
    setting = flat_yaml(SETTING_YAML.read_text(encoding="utf-8"))
    required = {k.lower() for k in REQUIRED_KEYS}
    missing = required - setting.keys()
    assert not missing, f"env/config/setting.yaml is missing keys: {missing}"
