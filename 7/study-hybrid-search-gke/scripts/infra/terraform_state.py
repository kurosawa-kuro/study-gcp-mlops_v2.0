"""Terraform state query / mutation helpers.

destroy_all / deploy_all から `terraform state list / rm` を呼ぶ業務ロジックを
集約。Phase 7 Run 4 で観測した「`-target` destroy が exit 0 でも cluster
unreachable で何も消えていなかった」「empty-state での destroy 再走で
依存閉包が recreate された」事故への対処を関数単位で再利用可能にする。

I/O 層 (subprocess による terraform CLI 呼び出し)。pure-data ではないので
`scripts/lib/` ではなく `scripts/infra/` に置く。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def state_list(infra_dir: Path, env: dict[str, str] | None = None) -> list[str]:
    """Return all addresses currently tracked in `terraform state`.

    `subprocess` の例外を吸収し、CLI 失敗時は空リストを返す。呼び出し側で
    state の有無を判定する用途で使う (空判定 = state 未初期化 or destroy 済)。

    ``env`` を渡すと subprocess の環境変数を上書きできる (現状コード内で
    アクティブな利用先は無いが、ad-hoc な ``TF_VAR_*`` 上書きを可能にする
    ための general-purpose hook として残す)。
    """
    proc = subprocess.run(
        ["terraform", f"-chdir={infra_dir}", "state", "list"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def state_size(infra_dir: Path, env: dict[str, str] | None = None) -> int:
    """Return the number of addresses in `terraform state`.

    Used to skip destroy when the previous run already cleared everything
    (idempotent destroy-all). Without this guard, re-running destroy on an
    empty state walks `-target` apply into the dependency closure and
    **recreates** targets, hitting WIF pool 30-day soft-delete (ADR 0003).
    """
    return len(state_list(infra_dir, env=env))


def addresses_starting_with(
    infra_dir: Path, prefix: str, env: dict[str, str] | None = None
) -> list[str]:
    """Return state addresses under a given module / type prefix.

    `prefix` には typically ``"module.kserve."`` のような module address +
    末尾 ``.`` を渡す。`-target` destroy が exit 0 でも cluster unreachable で
    実は何も消えなかったケース (Phase 7 Run 4 の `helm_release.kserve_crd`
    取りこぼし) を **exit code でなく state そのもの** で検知するための
    後方確認に使う。
    """
    return [addr for addr in state_list(infra_dir, env=env) if addr.startswith(prefix)]


def is_in_state(infra_dir: Path, address: str, env: dict[str, str] | None = None) -> bool:
    """True if ``address`` is currently tracked in `terraform state`."""
    return address in set(state_list(infra_dir, env=env))


def filter_targets_in_state(
    infra_dir: Path, candidates: list[str], env: dict[str, str] | None = None
) -> list[str]:
    """Filter ``candidates`` to keep only addresses currently in state.

    destroy step 4/6 の "state-flip only, no recreate" を honour するため、
    state にない address を `-target` で渡してはいけない (Terraform が依存
    閉包を pull して fresh instance を作る副作用がある — Phase 7 Run 4 で
    empty-state の destroy-all 再走 → 12 resources added の事故)。
    """
    in_state = set(state_list(infra_dir, env=env))
    return [t for t in candidates if t in in_state]


def state_rm(infra_dir: Path, address: str) -> bool:
    """Remove ``address`` (or a module subtree) from state. Return True on success.

    `terraform state rm` は module address (例: ``module.kserve``) を渡すと
    配下の全 resource を一括で剥がせる。targeted destroy が cluster
    unreachable で実 resource を消せなかった時の fallback として使う。
    """
    proc = subprocess.run(
        ["terraform", f"-chdir={infra_dir}", "state", "rm", address],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return True
    tail = (proc.stderr or "").strip().splitlines()[-3:]
    print(f"    state rm {address}: failed — {' / '.join(tail)}")
    return False
