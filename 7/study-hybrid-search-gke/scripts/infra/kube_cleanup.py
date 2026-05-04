"""Kubernetes finalizer cleanup for destroy-all.

Phase 7 Run 5 で踏んだ事故: `terraform destroy -target=module.kserve` は
`helm_release.kserve` (KServe operator) を最初に消す。operator が消えると
`kubectl apply -k infra/manifests/` で入れた InferenceService に紐づく
finalizer ``inferenceservice.finalizers`` を誰もクリアできなくなり、
`kubernetes_namespace.{search,inference}` の destroy が無限ループに陥る
(~3 分 retry のあとステップ全体が stall する)。同じ理由で ExternalSecret の
``externalsecrets.external-secrets.io/externalsecret-cleanup`` finalizer も
operator (external-secrets) 消滅後に取り残される。

対策: operator を destroy する前に、operator が watch しているカスタム
リソース (ISVC / ExternalSecret) を **operator に処理させて** 消しておく。
どちらも `kubectl delete --all -n <ns> --ignore-not-found` で operator が
finalizer を即座に処理するので、namespace の destroy が finalizer 待ちで
詰まらなくなる。

cluster が既に消滅している (前回 destroy-all が部分成功) ケースでは
`kubectl` が `connection refused` を返すため `check=False` で吸収する。
"""

from __future__ import annotations

import subprocess


def delete_orphan_workloads() -> None:
    """Pre-destroy: cluster-scoped CR を operator 健在のうちに掃除する。"""
    print("==>   pre-destroy: kubectl delete orphan workloads (avoid finalizer deadlock)")
    for cmd in (
        # ISVC: KServe operator が finalizer を持つ。operator が活きてる間に消す。
        [
            "kubectl",
            "delete",
            "inferenceservice",
            "--all",
            "--namespace=kserve-inference",
            "--ignore-not-found",
            "--timeout=60s",
        ],
        # ExternalSecret: external-secrets operator が finalizer を持つ。
        [
            "kubectl",
            "delete",
            "externalsecret",
            "--all",
            "--namespace=search",
            "--ignore-not-found",
            "--timeout=60s",
        ],
    ):
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if proc.stdout:
            print(f"    {proc.stdout.rstrip()}")
        if proc.returncode != 0:
            # cluster が既に無い / kubeconfig 未設定 / namespace 既消滅 を
            # 区別せず吸収。`check=False` の趣旨はあくまで destroy-all を
            # ブロックしないこと。
            stderr = (proc.stderr or "").strip()
            print(f"    (skip — kubectl returned rc={proc.returncode}: {stderr[:120]})")
