"""KubernetesPodOperator 共通ヘルパ — Phase 7 V5 fix (2026-05-03)。

過去 incident: 過去 session の Claude が DAG を `BashOperator: uv run python -m
scripts.X` で書いたが Composer worker は uv 不在 / repo source 不在で task
SUCCEEDED 未達 (= canonical 未達 = ゴール劣化)。本 module は DAG 各 task を
**KubernetesPodOperator** で実行する標準パターンを提供する:

- Composer Gen 3 の組み込み GKE 上で Pod を起動 (in_cluster=True デフォルト)
- image = `composer-runner` (Artifact Registry、`make build-composer-runner`)
- Pod は `composer-runner` image 内の Python venv で `python -m <module>` を実行
- env_variables (REGION / VERTEX_LOCATION / PIPELINE_ROOT_BUCKET 等) は
  Composer 環境から自動で Pod に inherit される (`env_from` で扱わず
  `KubernetesPodOperator(env_vars=...)` に渡す)
- Pod は sa-composer の Workload Identity を使う (= Composer 環境の SA と同じ
  権限。aiplatform.user / bigquery.jobUser / run.invoker 等)

詳細: docs/tasks/TASKS_ROADMAP.md §4.1 (V5 canonical 未達 fix)。
"""

from __future__ import annotations

import os

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator

# Composer 環境変数 (REGION / VERTEX_LOCATION / etc.) を Pod にも引き継ぐ。
# Composer Gen 3 が auto-inject する `GCP_PROJECT` も含める。
PROPAGATED_ENV_KEYS = (
    "GCP_PROJECT",
    "PROJECT_ID",
    "REGION",
    "VERTEX_LOCATION",
    "PIPELINE_ROOT_BUCKET",
    "PIPELINE_TEMPLATE_GCS_PATH",
    "VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME",
    "VERTEX_FEATURE_ONLINE_STORE_ID",
    "VERTEX_FEATURE_VIEW_ID",
    "API_EXTERNAL_URL",
    # V5 fix Run 2 fail postmortem (2026-05-03 晩): explicit API_URL パスで
    # default verify_tls=True / host_header=None になる問題を回避する補助 env。
    # composer/main.tf で値を seed (API_HOST_HEADER=search-api.example.com /
    # API_INSECURE_TLS=true)。
    "API_HOST_HEADER",
    "API_INSECURE_TLS",
    "SLO_AVAILABILITY_GOAL",
    "ENABLE_DAILY_VVS_REFRESH",
    "AUTO_PROMOTE",
    "APPLY",
)

# V5 fix (2026-05-03): scripts/_common.py の resolve_api_target() は `API_URL` env
# を読み、Composer kube context が無い Pod では gateway_url() の kubectl 経由
# resolve が失敗する。Composer 側 env_variables 名は `API_EXTERNAL_URL` (terraform
# canonical) を保ちつつ、Pod に inject する際に `API_URL` にも複製して
# scripts.ops.* が動くようにする。
ENV_KEY_ALIASES = {
    "API_EXTERNAL_URL": ("API_URL",),  # script 側 canonical
}


def _composer_runner_image() -> str:
    """`composer-runner` image URI (env override 可)。

    本番運用: `<region>-docker.pkg.dev/<project>/<repo>/composer-runner:latest`
    smoke / dev: `COMPOSER_RUNNER_IMAGE` env で上書き可。
    """
    override = os.environ.get("COMPOSER_RUNNER_IMAGE", "").strip()
    if override:
        return override
    # Composer Gen 3 が GCP_PROJECT を auto-set する。fallback で PROJECT_ID も見る。
    project = os.environ.get("GCP_PROJECT") or os.environ.get("PROJECT_ID") or "mlops-dev-a"
    region = os.environ.get("REGION", "asia-northeast1")
    repo = os.environ.get("ARTIFACT_REPO_ID", "mlops")
    return f"{region}-docker.pkg.dev/{project}/{repo}/composer-runner:latest"


def _propagated_env_vars() -> dict[str, str]:
    """Composer 環境の env_variables から PROPAGATED_ENV_KEYS を Pod に渡す。

    ENV_KEY_ALIASES に従い、scripts 側 canonical 名 (例: API_URL) にも複製する。

    V5 fix Run 3 fail postmortem (2026-05-03 晩): tf-apply で Composer
    env_variables に API_HOST_HEADER / API_INSECURE_TLS を追加しても、Composer
    scheduler の `os.environ` に即時反映されないケースが観測された (DIAG log
    で `<unset>` 確認)。timing 依存を避け、TLS / Host のような **値が
    決定的な env** は DAG file 内で hardcode default を持たせる (env が
    あればそれを優先、無ければ default fallback)。
    """
    # GKE Gateway 自己署名 TLS + HTTPRoute hostname の決定的 default。
    # `var.api_external_url` が GKE Gateway IP に向く前提のため、TLS verify は
    # 必ず off で、Host ヘッダは必ず DEFAULT_GATEWAY_HOST_HEADER 相当を付ける。
    HARDCODED_DEFAULTS = {
        "API_HOST_HEADER": "search-api.example.com",
        "API_INSECURE_TLS": "true",
    }
    out: dict[str, str] = dict(HARDCODED_DEFAULTS)
    for key in PROPAGATED_ENV_KEYS:
        if key in os.environ:
            value = os.environ[key]
            out[key] = value
            for alias in ENV_KEY_ALIASES.get(key, ()):
                out[alias] = value
    return out


def python_pod(
    *,
    task_id: str,
    module: str,
    extra_args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
) -> KubernetesPodOperator:
    """`composer-runner` image で `python -m <module>` を実行する Pod を返す。

    Args:
        task_id: DAG 上の task_id
        module: `python -m` で呼ぶ Python module path (例: ``scripts.ops.check_retrain``)
        extra_args: `python -m <module>` の後ろに付けたい追加 argv
        extra_env: PROPAGATED_ENV_KEYS 以外で task 固有に渡したい env (例: ``APPLY=1``)
    """
    args: list[str] = ["-m", module]
    if extra_args:
        args.extend(extra_args)

    env_vars = _propagated_env_vars()
    if extra_env:
        env_vars.update(extra_env)

    return KubernetesPodOperator(
        task_id=task_id,
        name=f"composer-{task_id}".replace("_", "-"),
        namespace="composer-user-workloads",
        image=_composer_runner_image(),
        cmds=["python"],
        arguments=args,
        env_vars=env_vars,
        # 本 image は `python:3.12-slim-bookworm` runtime + uv venv を /opt/venv に持つ。
        # service_account_name は Composer Gen 3 のデフォルト KSA (= sa-composer に
        # Workload Identity-bound) を使う。明示指定しない。
        get_logs=True,
        log_events_on_failure=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=300,
    )


def gcloud_pod(
    *,
    task_id: str,
    bash_command: str,
    extra_env: dict[str, str] | None = None,
) -> KubernetesPodOperator:
    """`composer-runner` image で gcloud CLI を実行する Pod を返す。

    Args:
        task_id: DAG 上の task_id
        bash_command: bash -c で渡す gcloud コマンド (例: ``gcloud dataform repositories ...``)
    """
    env_vars = _propagated_env_vars()
    if extra_env:
        env_vars.update(extra_env)

    return KubernetesPodOperator(
        task_id=task_id,
        name=f"composer-{task_id}".replace("_", "-"),
        namespace="composer-user-workloads",
        image=_composer_runner_image(),
        cmds=["bash"],
        arguments=["-lc", bash_command],
        env_vars=env_vars,
        get_logs=True,
        log_events_on_failure=True,
        is_delete_operator_pod=True,
        startup_timeout_seconds=300,
    )
