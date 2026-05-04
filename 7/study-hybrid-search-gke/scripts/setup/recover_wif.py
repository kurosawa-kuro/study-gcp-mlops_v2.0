"""Reconcile WIF pool / provider with Terraform state (PDCA loop safety).

GCP の WIF resource は **soft-delete (30 日保持)** で、destroy-all 後に
同じ ID を再作成しようとすると ``409 Requested entity already exists``
を返す。回避するには (a) 残存する resource を ``gcloud undelete`` で
ACTIVE に戻し (b) Terraform state に ``import`` して、次の plan/apply
で「create」ではなく「変更なし」になるようにする必要がある。

旧実装は **「state==DELETED の時だけ recover」**だったため、deploy-all
が部分失敗 → 再実行のシナリオで踏み抜けた事故 (Phase 7 Run 5):
- 1 回目: undelete 成功 / import 失敗 (cluster data source 不在)
- 2 回目: WIF state は ACTIVE (= undelete 済) → recover skip →
  tfstate に未 import のまま → ``terraform plan`` が「create」を保存
  → ``terraform apply`` が 409 で fail

新実装は **「GCP 側に存在する AND tfstate に未登録」** を import 条件
として、partial-success リトライでも吸収する:
1. ``gcloud describe`` で resource の現状 (ACTIVE / DELETED / 不在) を取得
2. DELETED なら undelete (ACTIVE 化)
3. tfstate に未登録なら ``state rm`` (no-op fallback) → ``import``

`scripts/setup/deploy_all.py` の step 3 から呼ばれる。manual recovery
tool としても `python -m scripts.setup.recover_wif` で実行可能。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts._common import env, run, terraform_var_args
from scripts.infra.terraform_state import is_in_state

INFRA = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"


def _gcloud_capture(args: list[str]) -> tuple[int, str]:
    """gcloud subprocess wrapper that returns (returncode, stripped_stdout).

    `scripts/_common.py::gcloud()` は capture=True で stdout のみ返すが、
    本 module は returncode で「resource そのものが存在しない」を判定する
    必要があるため、専用 wrapper を持つ。
    """
    proc = subprocess.run(
        ["gcloud", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout.strip()


def recover(project_id: str | None = None) -> None:
    """Reconcile WIF pool / provider with Terraform state.

    Phase 7 W3 cleanup: kubernetes/helm providers (provider.tf) now read
    endpoint+token from the local kubeconfig instead of the
    ``data.google_container_cluster`` data source. Without that data source
    the provider init no longer requires the GKE cluster to exist — so the
    ``TF_VAR_k8s_use_data_source=false`` placeholder mode that this module
    used to need is no longer required. Terraform `import` runs against the
    parent process env directly.
    """
    pid = project_id or env("PROJECT_ID")
    if not pid:
        raise SystemExit("[error] PROJECT_ID is empty")
    print("==> Recovery: reconcile WIF pool/provider with Terraform state")

    pool_address = "module.iam.google_iam_workload_identity_pool.github"
    pool_id = f"projects/{pid}/locations/global/workloadIdentityPools/github"
    pool_args = [
        "iam",
        "workload-identity-pools",
        "describe",
        "github",
        "--location=global",
        f"--project={pid}",
        "--format=value(state)",
    ]
    rc, pool_state = _gcloud_capture(pool_args)
    pool_exists_in_gcp = rc == 0 and pool_state in {"ACTIVE", "DELETED"}
    if pool_exists_in_gcp and pool_state == "DELETED":
        print("    pool soft-deleted → undelete to ACTIVE")
        run(
            [
                "gcloud",
                "iam",
                "workload-identity-pools",
                "undelete",
                "github",
                "--location=global",
                f"--project={pid}",
                "--quiet",
            ]
        )
    if pool_exists_in_gcp and not is_in_state(INFRA, pool_address):
        print(f"    pool exists in GCP but NOT in tfstate → import {pool_address}")
        subprocess.run(
            ["terraform", f"-chdir={INFRA}", "state", "rm", pool_address],
            check=False,
        )
        subprocess.run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "import",
                *terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL"),
                pool_address,
                pool_id,
            ],
            check=True,
        )

    provider_address = "module.iam.google_iam_workload_identity_pool_provider.github"
    provider_id = (
        f"projects/{pid}/locations/global/workloadIdentityPools/github/providers/github-oidc"
    )
    prov_args = [
        "iam",
        "workload-identity-pools",
        "providers",
        "describe",
        "github-oidc",
        "--workload-identity-pool=github",
        "--location=global",
        f"--project={pid}",
        "--format=value(expireTime)",
    ]
    rc, expire_time = _gcloud_capture(prov_args)
    # provider の `describe` は ACTIVE でも DELETED でも exit 0。`expireTime`
    # フィールドが付いてるのは soft-deleted 状態だけ。describe rc != 0 は
    # 「provider そのものが存在しない (=fresh project / 既に完全消滅)」を意味する。
    provider_exists_in_gcp = rc == 0
    if provider_exists_in_gcp and expire_time:
        print("    provider soft-deleted → undelete to ACTIVE")
        run(
            [
                "gcloud",
                "iam",
                "workload-identity-pools",
                "providers",
                "undelete",
                "github-oidc",
                "--workload-identity-pool=github",
                "--location=global",
                f"--project={pid}",
                "--quiet",
            ]
        )
    if provider_exists_in_gcp and not is_in_state(INFRA, provider_address):
        print(f"    provider exists in GCP but NOT in tfstate → import {provider_address}")
        subprocess.run(
            ["terraform", f"-chdir={INFRA}", "state", "rm", provider_address],
            check=False,
        )
        subprocess.run(
            [
                "terraform",
                f"-chdir={INFRA}",
                "import",
                *terraform_var_args("GITHUB_REPO", "ONCALL_EMAIL"),
                provider_address,
                provider_id,
            ],
            check=True,
        )


def main() -> int:
    recover()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
