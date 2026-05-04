"""Pin scripts/infra/{kube,gcs,vertex}_cleanup.py — destroy-all 用 cleanup.

destroy_all.py から切り出した cleanup 関数群が想定どおり gcloud /
kubectl をコールすることを subprocess mock で確認する。
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

from scripts.infra import gcs_cleanup, kube_cleanup, vertex_cleanup


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["x"], returncode=returncode, stdout=stdout, stderr="")


# ----- kube_cleanup ------


def test_delete_orphan_workloads_invokes_two_kubectl_deletes() -> None:
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _completed(stdout="deleted\n")

    with patch.object(subprocess, "run", side_effect=_fake_run):
        kube_cleanup.delete_orphan_workloads()

    assert len(calls) == 2
    # ISVC delete in kserve-inference namespace (preserves operator finalizer order)
    assert "inferenceservice" in calls[0]
    assert "--namespace=kserve-inference" in calls[0]
    assert "--ignore-not-found" in calls[0]
    # ExternalSecret delete in search namespace
    assert "externalsecret" in calls[1]
    assert "--namespace=search" in calls[1]


def test_delete_orphan_workloads_swallows_kubectl_failure(capsys) -> None:
    """cluster 不在で kubectl が rc!=0 を返しても destroy-all をブロックしない。"""

    def _fake_run(cmd, **kwargs):
        return _completed(returncode=1)

    with patch.object(subprocess, "run", side_effect=_fake_run):
        kube_cleanup.delete_orphan_workloads()  # must not raise

    captured = capsys.readouterr()
    assert "skip" in captured.out


# ----- gcs_cleanup ------


def test_wipe_bucket_passes_recursive_glob(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "p")
    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _completed()

    with patch.object(subprocess, "run", side_effect=_fake_run):
        gcs_cleanup.wipe_bucket("p", "p-models")

    cmd = captured["cmd"]
    assert "gcloud" in cmd[0]
    assert "storage" in cmd
    assert "rm" in cmd
    assert "--recursive" in cmd
    assert "--project=p" in cmd
    assert "gs://p-models/**" in cmd
    # `check=False` is set on `run()` call — verified via implicit absence
    # of CalledProcessError. We exercised that via _fake_run returning
    # rc=0; the contract test for rc!=0 is covered by `_common.run`.


def test_wipe_all_iterates_bucket_suffixes(monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_ID", "p")
    targets: list[str] = []

    def _fake_run(cmd, **kwargs):
        # Find the gs://... arg
        for arg in cmd:
            if arg.startswith("gs://"):
                targets.append(arg)
        return _completed()

    with patch.object(subprocess, "run", side_effect=_fake_run):
        gcs_cleanup.wipe_all_terraform_managed_buckets()

    assert targets == [
        "gs://p-models/**",
        "gs://p-artifacts/**",
        "gs://p-pipeline-root/**",
        "gs://p-meili-data/**",
    ]


# ----- vertex_cleanup ------


def test_undeploy_endpoint_models_skips_when_endpoint_absent(capsys) -> None:
    with patch.object(subprocess, "run", return_value=_completed(returncode=1)):
        vertex_cleanup.undeploy_endpoint_models("p", "asia-northeast1", "x-endpoint")
    out = capsys.readouterr().out
    assert "not present" in out


def test_undeploy_endpoint_models_skips_when_no_deployed(capsys) -> None:
    payload = json.dumps({"deployedModels": []})
    with patch.object(subprocess, "run", return_value=_completed(stdout=payload)):
        vertex_cleanup.undeploy_endpoint_models("p", "asia-northeast1", "x-endpoint")
    out = capsys.readouterr().out
    assert "no deployed_models" in out


def test_undeploy_endpoint_models_iterates_deployed_models() -> None:
    payload = json.dumps({"deployedModels": [{"id": "1", "displayName": "rerank-v1"}, {"id": "2"}]})
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        # First call is `describe`; subsequent are `undeploy-model`
        if "describe" in cmd:
            return _completed(stdout=payload)
        return _completed()

    with patch.object(subprocess, "run", side_effect=_fake_run):
        vertex_cleanup.undeploy_endpoint_models("p", "r", "ep1")

    undeploy_calls = [c for c in calls if "undeploy-model" in c]
    assert len(undeploy_calls) == 2
    # Each undeploy includes --deployed-model-id=<id>
    ids = [arg for c in undeploy_calls for arg in c if arg.startswith("--deployed-model-id=")]
    assert "--deployed-model-id=1" in ids
    assert "--deployed-model-id=2" in ids


def test_deployed_index_exists_reads_index_endpoint_payload() -> None:
    payload = json.dumps(
        [
            {"name": "ep-a", "deployedIndexes": [{"id": "property_embeddings_v3"}]},
            {"name": "ep-b", "deployedIndexes": [{"id": "other"}]},
        ]
    )
    with patch.object(subprocess, "run", return_value=_completed(stdout=payload)):
        assert vertex_cleanup.deployed_index_exists("p", "r", "property_embeddings_v3") is True
        assert vertex_cleanup.deployed_index_exists("p", "r", "missing") is False


def test_wait_for_deployed_index_absent_polls_until_stale_index_disappears() -> None:
    with (
        patch.object(
            vertex_cleanup,
            "deployed_index_state",
            side_effect=["transitional", "transitional", "absent"],
        ) as state_mock,
        patch.object(vertex_cleanup.time, "sleep") as sleep_mock,
        patch.object(
            vertex_cleanup.time,
            "monotonic",
            side_effect=[0.0, 1.0, 2.0, 3.0],
        ),
    ):
        vertex_cleanup.wait_for_deployed_index_absent("p", "r", "property_embeddings_v3")

    assert state_mock.call_count == 3
    assert sleep_mock.call_count == 2


def test_wait_for_deployed_index_absent_early_exits_on_ready_state() -> None:
    """Resume idempotency: 既に READY な DeployedIndex は wait しない。"""
    with (
        patch.object(
            vertex_cleanup,
            "deployed_index_state",
            return_value="ready",
        ) as state_mock,
        patch.object(vertex_cleanup.time, "sleep") as sleep_mock,
    ):
        vertex_cleanup.wait_for_deployed_index_absent("p", "r", "property_embeddings_v3")

    assert state_mock.call_count == 1
    assert sleep_mock.call_count == 0


def test_deployed_index_state_classifies_ready_vs_transitional() -> None:
    """`indexSyncTime` あり → ready / なし → transitional / 存在せず → absent."""
    payload_ready = json.dumps(
        [
            {
                "name": "ep-a",
                "deployedIndexes": [{"id": "x_v3", "indexSyncTime": "2026-05-03T00:00:00Z"}],
            }
        ]
    )
    payload_transitional = json.dumps([{"name": "ep-a", "deployedIndexes": [{"id": "x_v3"}]}])
    payload_absent = json.dumps([{"name": "ep-a", "deployedIndexes": []}])

    with patch.object(subprocess, "run", return_value=_completed(stdout=payload_ready)):
        assert vertex_cleanup.deployed_index_state("p", "r", "x_v3") == "ready"
    with patch.object(subprocess, "run", return_value=_completed(stdout=payload_transitional)):
        assert vertex_cleanup.deployed_index_state("p", "r", "x_v3") == "transitional"
    with patch.object(subprocess, "run", return_value=_completed(stdout=payload_absent)):
        assert vertex_cleanup.deployed_index_state("p", "r", "x_v3") == "absent"
