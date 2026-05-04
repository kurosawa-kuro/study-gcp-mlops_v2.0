"""Pin scripts/infra/terraform_state.py — state query / mutation helpers.

destroy_all で「`-target` destroy が exit 0 でも何も消えていなかった」
「empty-state での destroy 再走で依存閉包が recreate された」事故への
構造的対処として state 操作を独立 module に切り出した。本テストは
subprocess を mock して、各 helper が想定どおりに `terraform state list`
の出力を解釈することを pin する。
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.infra import terraform_state as ts


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["terraform"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_state_list_returns_empty_on_cli_failure() -> None:
    with patch.object(subprocess, "run", return_value=_completed("", returncode=1)):
        assert ts.state_list(Path("/x")) == []


def test_state_list_returns_lines_when_present() -> None:
    out = "module.iam.foo\n\nmodule.gke.bar\n"
    with patch.object(subprocess, "run", return_value=_completed(out)):
        assert ts.state_list(Path("/x")) == ["module.iam.foo", "module.gke.bar"]


def test_state_size_counts_addresses() -> None:
    with patch.object(subprocess, "run", return_value=_completed("a\nb\nc\n")):
        assert ts.state_size(Path("/x")) == 3


def test_state_size_zero_on_cli_failure() -> None:
    with patch.object(subprocess, "run", return_value=_completed("", returncode=2)):
        assert ts.state_size(Path("/x")) == 0


def test_addresses_starting_with_filters_by_prefix() -> None:
    out = "module.kserve.helm_release.kserve_crd\nmodule.iam.foo\nmodule.kserve.kubernetes_namespace.search\n"
    with patch.object(subprocess, "run", return_value=_completed(out)):
        result = ts.addresses_starting_with(Path("/x"), "module.kserve.")
    assert result == [
        "module.kserve.helm_release.kserve_crd",
        "module.kserve.kubernetes_namespace.search",
    ]


def test_is_in_state_true_when_address_present() -> None:
    out = "module.iam.foo\nmodule.gke.bar\n"
    with patch.object(subprocess, "run", return_value=_completed(out)):
        assert ts.is_in_state(Path("/x"), "module.iam.foo") is True
        assert ts.is_in_state(Path("/x"), "module.iam.absent") is False


def test_filter_targets_keeps_only_in_state() -> None:
    out = "module.data.google_bigquery_table.t1\nmodule.data.google_bigquery_table.t2\n"
    candidates = [
        "module.data.google_bigquery_table.t1",
        "module.data.google_bigquery_table.absent",
        "module.data.google_bigquery_table.t2",
    ]
    with patch.object(subprocess, "run", return_value=_completed(out)):
        result = ts.filter_targets_in_state(Path("/x"), candidates)
    assert result == [
        "module.data.google_bigquery_table.t1",
        "module.data.google_bigquery_table.t2",
    ]


def test_state_rm_returns_true_on_success() -> None:
    with patch.object(subprocess, "run", return_value=_completed("ok\n")):
        assert ts.state_rm(Path("/x"), "module.kserve") is True


def test_state_rm_returns_false_on_failure(capsys) -> None:
    proc = subprocess.CompletedProcess(
        args=["terraform"], returncode=1, stdout="", stderr="failure msg\n"
    )
    with patch.object(subprocess, "run", return_value=proc):
        assert ts.state_rm(Path("/x"), "module.kserve") is False
    captured = capsys.readouterr()
    assert "failed" in captured.out


def test_state_list_passes_env_when_supplied() -> None:
    """env は subprocess に丸ごと渡る (recover_wif の no-cluster placeholder)。"""
    captured: dict = {}

    def _fake_run(*args, **kwargs):
        captured["env"] = kwargs.get("env")
        return _completed("")

    with patch.object(subprocess, "run", side_effect=_fake_run):
        ts.state_list(Path("/x"), env={"TF_VAR_k8s_use_data_source": "false"})
    assert captured["env"] == {"TF_VAR_k8s_use_data_source": "false"}
