"""Generate infra/manifests/search-api/configmap.example.yaml from setting.yaml.

Why a generator instead of hand-editing:
- ``project_id`` must match ``env/config/setting.yaml`` (single source of
  truth) so a one-line edit there propagates to the manifest.
- ``models_bucket`` follows the convention ``<project_id>-models`` set in
  ``ml/common/config/base.py::BaseAppSettings.gcs_models_bucket`` default.
  Hardcoding it in the manifest is a drift trap.
- ``meili_base_url`` is environment-specific (Cloud Run URL set per
  deploy) so we keep a placeholder constant. The expectation is documented
  inline so operators know what to overlay before ``make apply-manifests``.

Pair with ``tests/integration/infra/test_configmap_drift.py`` which fails
CI if the generator output drifts from the committed file.

The actual ConfigMap schema (key list / defaults / YAML rendering) lives in
``scripts/lib/config.py`` so that ``scripts/setup/deploy_all.py`` runtime
overlay shares the same source. Phase 7 W2-5 saw a drift between this
generator and the deploy_all overlay; consolidating into ``scripts/lib/``
makes that class of bug structurally impossible.
"""

from __future__ import annotations

from pathlib import Path

from scripts._common import DEFAULTS
from scripts.lib.config import generate_configmap_data, render_configmap_yaml

OUTPUT = (
    Path(__file__).resolve().parent.parent.parent
    / "infra"
    / "manifests"
    / "search-api"
    / "configmap.example.yaml"
)

# Placeholder kept in the example file. Operators overlay the real Cloud
# Run URL via env-specific kustomization or `kubectl create configmap
# --from-literal` before applying.
MEILI_BASE_URL_PLACEHOLDER = "https://meili-search-XXXXX-an.a.run.app"


def render() -> str:
    project_id = DEFAULTS.get("PROJECT_ID")
    if not project_id:
        raise SystemExit("env/config/setting.yaml is missing required key: project_id")
    models_bucket = f"{project_id}-models"
    data = generate_configmap_data(
        project_id=project_id,
        models_bucket=models_bucket,
        meili_base_url=MEILI_BASE_URL_PLACEHOLDER,
    )
    return render_configmap_yaml(data, with_header=True)


def main() -> int:
    content = render()
    rel = OUTPUT.relative_to(OUTPUT.parents[3])
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == content:
        print(f"==> {rel} already up to date")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"==> wrote {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
