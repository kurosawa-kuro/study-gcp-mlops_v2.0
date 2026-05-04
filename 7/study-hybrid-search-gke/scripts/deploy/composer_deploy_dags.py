"""Upload pipeline/dags/*.py to the Composer DAG GCS bucket.

Phase 7 W2-4 Stage 2: Cloud Composer 環境を Terraform で立てた後、本 script が
``pipeline/dags/`` 配下の DAG ファイルを ``terraform output composer_dag_bucket``
が指す GCS bucket へ upload する (Composer scheduler が GCS を polling して
DAG を再 parse する仕組み)。

Idempotent — DAG ファイルは GCS object 上書き可なので、何度叩いても安全。

`enable_composer=false` のときは ``composer_dag_bucket`` output が空文字に
なるため early-return する (Stage 1 / Stage 2 段階での deploy_all 互換性
のため)。

DAG パッケージ階層 (2026-05-03 incident 対策): DAG ファイルは
``from pipeline.dags._common import ...`` / ``from pipeline.dags._pod import ...``
の絶対 import を使うため、Composer DAG bucket 上にも ``pipeline/__init__.py``
+ ``pipeline/dags/__init__.py`` + ``pipeline/dags/_common.py``
+ ``pipeline/dags/_pod.py`` の階層を保持して upload する必要がある
(``/home/airflow/gcs/dags/`` が Composer の ``sys.path`` に含まれるため、
``pipeline`` パッケージとして import 可能)。flat upload だと
``ModuleNotFoundError: No module named 'pipeline'`` で DagBag に登録されず、
``airflow dags list-import-errors`` に並ぶ。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts._common import run

INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"
REPO_ROOT = Path(__file__).resolve().parents[2]
DAGS_DIR = REPO_ROOT / "pipeline" / "dags"
PIPELINE_PKG_INIT = REPO_ROOT / "pipeline" / "__init__.py"


def _terraform_output(name: str) -> str:
    """Read a single terraform output as a string. Empty string when unset."""
    proc = run(
        ["terraform", f"-chdir={INFRA}", "output", "-json"],
        capture=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"[error] terraform output -json failed (rc={proc.returncode})")
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[error] terraform output JSON decode failed: {exc}") from exc
    entry = payload.get(name)
    if entry is None or not isinstance(entry, dict):
        return ""
    value = entry.get("value", "")
    return str(value or "")


def _list_top_level_dag_files() -> list[Path]:
    """Return top-level DAG .py files (Airflow が DagBag scan する entrypoint).

    `_common.py` / `__init__.py` 等は Airflow が DAG として誤認しないよう除外
    (top-level dags/ には絶対 import で参照される ``pipeline.dags._common``
    の方を pipeline パッケージ階層として別経路で upload する)。
    """
    return sorted(
        p
        for p in DAGS_DIR.glob("*.py")
        if not p.name.startswith("_") and not p.name.startswith("__pycache__")
    )


def _list_pipeline_pkg_files() -> list[tuple[Path, str]]:
    """Return (local_path, gcs_relative_path) for the pipeline package shim.

    Composer DAG bucket では ``/home/airflow/gcs/dags/`` が ``sys.path`` に
    含まれるため、その配下に ``pipeline/__init__.py`` + ``pipeline/dags/__init__.py``
    + ``pipeline/dags/_common.py`` + ``pipeline/dags/_pod.py`` を置けば
    ``from pipeline.dags._common import ...`` / ``from pipeline.dags._pod import ...``
    で resolve される。
    """
    return [
        (PIPELINE_PKG_INIT, "pipeline/__init__.py"),
        (DAGS_DIR / "__init__.py", "pipeline/dags/__init__.py"),
        (DAGS_DIR / "_common.py", "pipeline/dags/_common.py"),
        # V5 fix (2026-05-03、§4.1): KubernetesPodOperator helper。
        # 旧 BashOperator + uv run path は Composer worker 非互換のため、
        # 新版の各 DAG は ``from pipeline.dags._pod import python_pod`` を
        # 絶対 import する。pkg layout を保ったまま upload する必要あり。
        (DAGS_DIR / "_pod.py", "pipeline/dags/_pod.py"),
    ]


def _list_data_files() -> list[tuple[Path, str]]:
    """Return (local_path, data_relative_path) for non-DAG asset uploads.

    Composer は DAG bucket と並列に ``data/`` GCS subpath を持ち、Composer
    pod 上では ``/home/airflow/gcs/data/`` に mount される (``gcsDataPrefix``)。
    DAG が parse 時に ``read_text()`` で開く SQL ファイル等はここに upload
    する (DAG bucket に置くと Airflow が DAG として scan しに行く)。

    2026-05-03 incident: ``monitoring_validation.py`` が repo path
    ``infra/sql/monitoring/*.sql`` を直接 ``read_text()`` していて
    ``FileNotFoundError`` で DagBag に登録されなかった。
    """
    sql_dir = REPO_ROOT / "infra" / "sql" / "monitoring"
    return [
        (sql_path, f"infra/sql/monitoring/{sql_path.name}")
        for sql_path in sorted(sql_dir.glob("*.sql"))
    ]


def main(argv: list[str] | None = None) -> int:
    del argv  # CLI args 未使用 (terraform output のみで完結)

    dag_bucket = _terraform_output("composer_dag_bucket")
    if not dag_bucket:
        print(
            "[info] composer_dag_bucket output is empty — Composer environment not provisioned "
            "(enable_composer=false?). Skipping DAG upload."
        )
        return 0

    dag_files = _list_top_level_dag_files()
    if not dag_files:
        print(f"[warn] no DAG files found under {DAGS_DIR}")
        return 0

    print(f"[info] uploading {len(dag_files)} DAG file(s) + pipeline package shim → {dag_bucket}")
    for dag_file in dag_files:
        print(f"  + {dag_file.name}")

    proc = run(
        ["gsutil", "-m", "cp", *(str(p) for p in dag_files), dag_bucket],
        capture=False,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"[error] gsutil cp DAG entrypoints failed (rc={proc.returncode})")

    pkg_bucket_root = dag_bucket.rstrip("/")
    for local_path, gcs_relative in _list_pipeline_pkg_files():
        target = f"{pkg_bucket_root}/{gcs_relative}"
        print(f"  + {gcs_relative}")
        proc = run(["gsutil", "cp", str(local_path), target], capture=False, check=False)
        if proc.returncode != 0:
            raise SystemExit(f"[error] gsutil cp {gcs_relative} failed (rc={proc.returncode})")

    # Composer data folder ( gs://<env>/data/ ) — DAG が read_text() で開く
    # 非 DAG アセット (SQL 等) を ここに置く (DAG bucket に置くと Airflow が
    # DAG として scan しに行くため分離が必要)。
    data_bucket_root = pkg_bucket_root.rsplit("/dags", 1)[0] + "/data"
    data_files = _list_data_files()
    if data_files:
        print(f"[info] uploading {len(data_files)} data file(s) → {data_bucket_root}")
        for local_path, data_relative in data_files:
            target = f"{data_bucket_root}/{data_relative}"
            print(f"  + {data_relative}")
            proc = run(["gsutil", "cp", str(local_path), target], capture=False, check=False)
            if proc.returncode != 0:
                raise SystemExit(
                    f"[error] gsutil cp data {data_relative} failed (rc={proc.returncode})"
                )

    print(
        f"[info] composer-deploy-dags complete ({len(dag_files)} DAG files + "
        f"pipeline shim + {len(data_files)} data files)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
