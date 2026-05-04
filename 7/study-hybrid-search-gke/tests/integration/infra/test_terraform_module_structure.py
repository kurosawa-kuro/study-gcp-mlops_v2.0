"""Terraform module-structure invariants.

Each sub-module under ``infra/terraform/modules/`` must carry the 4-file convention:
``main.tf`` / ``variables.tf`` / ``outputs.tf`` / ``versions.tf``. Every
variable must have a ``description`` attribute so module consumers see intent
without reading implementation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULES_DIR = REPO_ROOT / "infra" / "terraform" / "modules"

REQUIRED_FILES = ("main.tf", "variables.tf", "outputs.tf", "versions.tf")

_VARIABLE_BLOCK_RE = re.compile(
    r'variable\s+"(?P<name>[^"]+)"\s*\{(?P<body>.*?)\n\}',
    re.DOTALL,
)


def _modules() -> list[Path]:
    return sorted(p for p in MODULES_DIR.iterdir() if p.is_dir())


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
@pytest.mark.parametrize("filename", REQUIRED_FILES)
def test_module_has_required_file(module: Path, filename: str) -> None:
    assert (module / filename).is_file(), (
        f"module {module.name} is missing {filename}. "
        "Every module under infra/terraform/modules/ must carry main.tf / variables.tf / outputs.tf / versions.tf."
    )


@pytest.mark.parametrize("module", _modules(), ids=lambda p: p.name)
def test_every_variable_has_description(module: Path) -> None:
    variables_tf = module / "variables.tf"
    if not variables_tf.exists():
        pytest.skip("variables.tf missing (caught by the structure test)")
    text = variables_tf.read_text()
    missing: list[str] = []
    for match in _VARIABLE_BLOCK_RE.finditer(text):
        name = match["name"]
        body = match["body"]
        if "description" not in body:
            missing.append(name)
    assert not missing, (
        f"module {module.name}: variables without a description — {missing}. "
        'Add a `description = "..."` line so module consumers see intent.'
    )
