"""Pin scripts/deploy/composer_deploy_dags.py — DAG GCS upload helper (Phase 7 W2-4).

検証:
- `terraform output composer_dag_bucket` が空文字 → early-return (rc=0)
  (Stage 1 / Stage 2 の `enable_composer=false` default 時に deploy_all を
  壊さない設計)
- terraform output が GCS prefix を返す → `gsutil cp` で `pipeline/dags/*.py`
  を upload (各 DAG file が `gsutil` 引数に並ぶ)
- DAG file 列挙が `__pycache__/` を除外する
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.deploy import composer_deploy_dags


def _fake_run_factory(stdout: str, returncode: int = 0):
    def _fake_run(cmd, capture=False, check=False):
        proc = MagicMock()
        proc.stdout = stdout
        proc.returncode = returncode
        return proc

    return _fake_run


def test_main_early_returns_when_dag_bucket_empty(monkeypatch, capsys) -> None:
    """`composer_dag_bucket=""` (= enable_composer=false) のとき rc=0 で skip。"""
    monkeypatch.setattr(
        composer_deploy_dags,
        "run",
        _fake_run_factory(stdout=json.dumps({})),
    )
    rc = composer_deploy_dags.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert "Composer environment not provisioned" in captured.out


def test_main_uploads_dags_when_bucket_set(monkeypatch, capsys) -> None:
    """`composer_dag_bucket=gs://...` が返ったとき DAG entrypoint + pipeline shim
    + data files (SQL) を `gsutil cp` で upload する。"""
    calls: list[list[str]] = []

    def _fake_run(cmd, capture=False, check=False):
        calls.append(list(cmd))
        proc = MagicMock()
        proc.returncode = 0
        if cmd[0] == "terraform":
            proc.stdout = json.dumps(
                {"composer_dag_bucket": {"value": "gs://composer-bucket/dags"}}
            )
        else:
            proc.stdout = ""
        return proc

    monkeypatch.setattr(composer_deploy_dags, "run", _fake_run)
    rc = composer_deploy_dags.main()
    assert rc == 0

    upload_calls = [c for c in calls if c[0] == "gsutil"]
    assert upload_calls, "no gsutil calls observed"

    # DAG entrypoints — first call uses `-m cp` (multi-file upload to top-level dags/)
    entrypoint_call = upload_calls[0]
    assert entrypoint_call[:3] == ["gsutil", "-m", "cp"]
    assert entrypoint_call[-1] == "gs://composer-bucket/dags"
    joined_entrypoints = " ".join(entrypoint_call)
    for required_dag in (
        "daily_feature_refresh.py",
        "retrain_orchestration.py",
        "monitoring_validation.py",
    ):
        assert required_dag in joined_entrypoints, (
            f"missing DAG entrypoint in upload args: {required_dag}"
        )
    # `_common.py` / `__init__.py` は entrypoint upload には含めない (Airflow が
    # DAG として誤認しないよう、別途 pipeline package shim として upload する)
    for excluded in ("_common.py", "__init__.py"):
        assert excluded not in joined_entrypoints, (
            f"{excluded} must NOT be uploaded as a DAG entrypoint"
        )

    # pipeline package shim — 個別 `gsutil cp` で階層保持
    pkg_targets = [c for c in upload_calls[1:] if any("pipeline/" in arg for arg in c)]
    pkg_paths = sorted(c[-1].rsplit("/", 1)[-1] for c in pkg_targets)
    expected_pkg = {
        "__init__.py",  # pipeline/__init__.py + pipeline/dags/__init__.py
        "_common.py",
    }
    assert expected_pkg.issubset(set(pkg_paths)), (
        f"pipeline package shim missing files: have={pkg_paths}"
    )

    # data files (SQL) は composer data folder へ upload
    data_targets = [c for c in upload_calls[1:] if "/data/" in c[-1]]
    assert data_targets, "no data file uploads observed (SQL must go to composer data/)"
    for data_call in data_targets:
        assert data_call[-1].startswith("gs://composer-bucket/data/")

    captured = capsys.readouterr()
    assert "uploading" in captured.out
    assert "composer-deploy-dags complete" in captured.out


def test_main_raises_when_terraform_output_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        composer_deploy_dags,
        "run",
        _fake_run_factory(stdout="", returncode=1),
    )
    with pytest.raises(SystemExit, match="terraform output -json failed"):
        composer_deploy_dags.main()


def test_main_raises_on_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        composer_deploy_dags,
        "run",
        _fake_run_factory(stdout="not valid json"),
    )
    with pytest.raises(SystemExit, match="terraform output JSON decode failed"):
        composer_deploy_dags.main()


def test_top_level_dag_listing_excludes_underscore_files() -> None:
    """top-level DAG entrypoint は `_` 始まり (= `_common.py` / `__init__.py`)
    と `__pycache__` を除外する (Airflow が DAG として誤認しないため)。"""
    files = composer_deploy_dags._list_top_level_dag_files()
    assert files, "no DAG entrypoints found"
    names = {p.name for p in files}
    assert "_common.py" not in names
    assert "__init__.py" not in names
    assert all(not p.name.startswith("_") for p in files)
    assert all("__pycache__" not in str(p) for p in files)
    for p in files:
        assert isinstance(p, Path)
        assert p.is_file()


def test_pipeline_pkg_files_listed_with_gcs_relative_paths() -> None:
    """`pipeline/__init__.py` + `pipeline/dags/__init__.py` + `pipeline/dags/_common.py`
    + `pipeline/dags/_pod.py` の 4 件を、Composer DAG bucket 上の階層 (`pipeline/...`)
    を保持して upload する (V5: `python_pod` helper)。"""
    pkg = composer_deploy_dags._list_pipeline_pkg_files()
    relatives = sorted(rel for _, rel in pkg)
    assert relatives == [
        "pipeline/__init__.py",
        "pipeline/dags/__init__.py",
        "pipeline/dags/_common.py",
        "pipeline/dags/_pod.py",
    ]
    for local_path, _ in pkg:
        assert local_path.is_file(), f"pipeline pkg shim file missing: {local_path}"


def test_data_files_listed_for_sql_assets() -> None:
    """SQL ファイル (DAG が `read_text()` で開く asset) は Composer の data/
    folder へ upload する事を pin。DAG bucket に置くと Airflow が DAG として
    scan してしまうため分離が必須 (2026-05-03 incident)。"""
    data = composer_deploy_dags._list_data_files()
    relatives = sorted(rel for _, rel in data)
    assert "infra/sql/monitoring/validate_feature_skew.sql" in relatives
    assert "infra/sql/monitoring/validate_model_output_drift.sql" in relatives
    for local_path, _ in data:
        assert local_path.is_file(), f"data file missing: {local_path}"
