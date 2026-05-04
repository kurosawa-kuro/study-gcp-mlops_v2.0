"""Shared live checks for Phase 7 opt-in e2e (ConfigMap + canonical ops gates).

Used by:

- ``test_phase7_acceptance_gate`` — **existing** deploy (no destroy in test)
- ``test_phase7_full_recreate_gate`` — destroy → deploy → same checks
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_phase7_live_acceptance_checks(repo_root: Path) -> None:
    """Assume cluster + search-api already deployed; validate canonical path."""
    proc = subprocess.run(
        ["kubectl", "get", "configmap", "-n", "search", "search-api-config", "-o", "yaml"],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).splitlines()[-40:])
        raise AssertionError(f"kubectl get configmap failed rc={proc.returncode}\n{tail}")
    configmap_yaml = proc.stdout or ""
    for key in (
        "vertex_vector_search_index_endpoint_id",
        "vertex_vector_search_deployed_index_id",
        "vertex_feature_online_store_id",
        "vertex_feature_view_id",
        "vertex_feature_online_store_endpoint",
    ):
        assert f"{key}: " in configmap_yaml, f"ConfigMap missing key {key}"
        assert f'{key}: ""' not in configmap_yaml, (
            f"ConfigMap key {key} is empty — configmap_overlay didn't inject Terraform output"
        )

    _run(repo_root, ["make", "ops-search-components"], timeout=300)
    _run(
        repo_root,
        ["uv", "run", "python", "-m", "scripts.ops.vertex.vector_search"],
        timeout=300,
    )
    _run(repo_root, ["make", "ops-vertex-feature-group"], timeout=300)
    _run(repo_root, ["make", "ops-feedback"], timeout=300)
    _run(repo_root, ["make", "ops-ranking"], timeout=300)
    _run(repo_root, ["make", "ops-accuracy-report"], timeout=300)


def _run(repo_root: Path, cmd: list[str], *, timeout: int) -> None:
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        tail = "\n".join(out.splitlines()[-40:])
        raise AssertionError(f"command failed rc={proc.returncode}: {' '.join(cmd)}\n{tail}")
