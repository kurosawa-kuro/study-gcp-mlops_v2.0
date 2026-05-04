"""Generate pipeline/data_job/dataform/workflow_settings.yaml from setting.yaml.

Dataform's workflow_settings.yaml has a fixed schema (defaultProject /
defaultLocation / defaultDataset / defaultAssertionDataset / dataformCoreVersion)
which prevents using YAML aliases. To keep env/config/setting.yaml as the
single source of truth for project_id / region etc., we render the Dataform
file from a small in-script template each time `make sync-dataform-config`
runs. The matching test (tests/test_dataform_workflow_settings.py) fails CI
if the two files drift.
"""

from __future__ import annotations

from pathlib import Path

from scripts._common import DEFAULTS

OUTPUT = (
    Path(__file__).resolve().parent.parent.parent
    / "pipeline"
    / "data_job"
    / "dataform"
    / "workflow_settings.yaml"
)

REQUIRED_KEYS = (
    "PROJECT_ID",
    "REGION",
    "DATAFORM_DEFAULT_DATASET",
    "DATAFORM_DEFAULT_ASSERTION_DATASET",
    "DATAFORM_CORE_VERSION",
)


def render() -> str:
    """Build the workflow_settings.yaml content from DEFAULTS."""
    missing = [k for k in REQUIRED_KEYS if not DEFAULTS.get(k)]
    if missing:
        raise SystemExit(
            f"env/config/setting.yaml is missing required keys for Dataform: {missing}"
        )
    return (
        "# AUTO-GENERATED from env/config/setting.yaml — do NOT edit by hand.\n"
        "# Run `make sync-dataform-config` to regenerate after changing setting.yaml.\n"
        f"defaultProject: {DEFAULTS['PROJECT_ID']}\n"
        f"defaultLocation: {DEFAULTS['REGION']}\n"
        f"defaultDataset: {DEFAULTS['DATAFORM_DEFAULT_DATASET']}\n"
        f"defaultAssertionDataset: {DEFAULTS['DATAFORM_DEFAULT_ASSERTION_DATASET']}\n"
        f"dataformCoreVersion: {DEFAULTS['DATAFORM_CORE_VERSION']}\n"
    )


def main() -> int:
    content = render()
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == content:
        print(f"==> {OUTPUT.relative_to(OUTPUT.parent.parent)} already up to date")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"==> wrote {OUTPUT.relative_to(OUTPUT.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
