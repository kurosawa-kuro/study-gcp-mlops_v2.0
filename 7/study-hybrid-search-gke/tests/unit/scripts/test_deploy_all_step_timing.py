"""Per-step timing in ``scripts.setup.deploy_all``.

When ``make deploy-all`` hangs in production, operators need to know WHICH
step is slow. The ``_step`` + ``_step_done`` helpers emit elapsed-time anchors
that ``scripts.deploy.monitor`` parses + operators grep in raw logs. These
tests pin the emitted line format so refactors don't silently break both
consumers.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from scripts.setup import deploy_all as dall


@pytest.fixture(autouse=True)
def _reset_globals() -> None:
    dall._DEPLOY_ALL_STARTED_AT = None
    dall._STEP_STARTED_AT = None


def test_step_first_call_emits_header_without_elapsed_anchor(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Step 1 has no "prev_step_elapsed" / "total_elapsed" line because there
    is no previous step to anchor against."""
    dall._step(1, 7, "tf-bootstrap")
    out = capsys.readouterr().out
    assert "step 1/7: tf-bootstrap" in out
    assert "prev_step_elapsed" not in out, (
        "Step 1 must not emit prev_step_elapsed (there is no previous step)."
    )


def test_step_subsequent_calls_emit_elapsed_anchor(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Steps 2..N must emit prev_step_elapsed= + total_elapsed= so operators
    can see WHICH step is slow when they tail the log. Simulated clock jumps
    from t=100 (step 1 start) to t=300 (step 2 start) → prev elapsed 200s.
    """
    # Drive the module-level monotonic clock for both step entries so the
    # arithmetic is deterministic regardless of wall-clock drift.
    with patch("scripts.setup.deploy_all.time.monotonic", side_effect=[100.0, 300.0]):
        dall._step(1, 3, "first")
        dall._step(2, 3, "second")
    out = capsys.readouterr().out
    assert "step 2/3: second" in out
    anchor = re.search(r"prev_step_elapsed=(\d+)s\s+total_elapsed=(\d+)s", out)
    assert anchor is not None, f"Missing elapsed anchor in step 2 output:\n{out}"
    assert anchor.group(1) == "200", f"prev_step_elapsed should be 200s, got {anchor.group(1)}"
    assert anchor.group(2) == "200", f"total_elapsed should be 200s, got {anchor.group(2)}"


def test_step_done_emits_elapsed_line_matching_monitor_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``scripts.deploy.monitor`` could in the future grep for
    ``deploy-all  step-done elapsed=<n>s``. Pin the exact prefix so refactors
    that change the spacing / label don't silently break log parsing.
    """
    dall._step(1, 2, "tf-bootstrap")
    dall._step_done()
    out = capsys.readouterr().out
    assert re.search(r"deploy-all\s+step-done\s+elapsed=\d+s", out), (
        f"step-done line missing or format changed:\n{out}"
    )


def test_step_done_noop_before_any_step() -> None:
    """Calling _step_done before any _step must be safe (no crash, no bogus
    "elapsed=4000000000s" from uninitialized monotonic baseline).
    """
    # No _step called → _STEP_STARTED_AT is None → _step_done silently no-ops.
    dall._step_done()  # must not raise


def test_resolve_step_ref_accepts_number_and_name() -> None:
    steps = dall._steps()
    assert dall._resolve_step_ref("4", steps) == 4
    assert dall._resolve_step_ref("sync-dataform", steps) == 4


def test_main_honors_from_step_and_to_step(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def _runner(name: str):
        def _run() -> int:
            calls.append(name)
            return 0

        return _run

    steps = [
        dall.DeployStep(1, "one", "one", _runner("one")),
        dall.DeployStep(2, "two", "two", _runner("two")),
        dall.DeployStep(3, "three", "three", _runner("three")),
    ]

    with (
        patch(
            "scripts.setup.deploy_all._parse_args",
            return_value=type("Args", (), {"from_step": "2", "to_step": "3"})(),
        ),
        patch("scripts.setup.deploy_all._steps", return_value=steps),
    ):
        rc = dall.main()

    out = capsys.readouterr().out
    assert rc == 0
    assert calls == ["two", "three"]
    assert "from_step=2 to_step=3" in out


def test_main_prints_failure_summary_for_nonzero_step(
    capsys: pytest.CaptureFixture[str],
) -> None:
    steps = [
        dall.DeployStep(1, "one", "one", lambda: 0),
        dall.DeployStep(2, "broken", "broken", lambda: 7),
    ]

    with (
        patch(
            "scripts.setup.deploy_all._parse_args",
            return_value=type("Args", (), {"from_step": "1", "to_step": "2"})(),
        ),
        patch("scripts.setup.deploy_all._steps", return_value=steps),
    ):
        rc = dall.main()

    out = capsys.readouterr().out
    assert rc == 7
    assert "deploy-all FAILED at step 2 (broken)" in out


def test_run_tf_apply_uses_staged_apply_and_waits_for_readiness() -> None:
    stage1_calls: list[list[str]] = []
    stage2_calls: list[list[str]] = []

    def _fake_stage1(args: list[str], **_: object) -> None:
        stage1_calls.append(args)

    def _fake_stream(cmd: list[str], **_: object) -> None:
        stage2_calls.append(cmd)

    with (
        patch.dict(
            "os.environ",
            {
                "PROJECT_ID": "mlops-test",
                "REGION": "asia-northeast1",
                "GKE_CLUSTER_NAME": "hybrid-search",
                "VERTEX_VECTOR_SEARCH_DEPLOYED_INDEX_ID": "property_embeddings_v3",
            },
            clear=False,
        ),
        patch(
            "scripts.setup.deploy_all.terraform_apply_stage1_with_retries",
            side_effect=_fake_stage1,
        ),
        patch(
            "scripts.setup.deploy_all.run_terraform_streaming_with_lock_retry",
            side_effect=_fake_stream,
        ),
        patch("scripts.setup.deploy_all.wait_for_deployed_index_absent") as wait_vvs,
        patch("scripts.setup.deploy_all.ensure_kubectl_context") as ensure_ctx,
        patch("scripts.setup.deploy_all.wait_until_api_ready") as wait_k8s,
        patch("scripts.setup.deploy_all.recover_orphan_gcp_resources", return_value=0),
        patch("scripts.setup.deploy_all.import_persistent_vvs_resources", return_value=0),
        patch("scripts.setup.deploy_all.wait_until_feature_store_names_released"),
    ):
        assert dall._run_tf_apply() == 0

    wait_vvs.assert_called_once_with("mlops-test", "asia-northeast1", "property_embeddings_v3")
    ensure_ctx.assert_called_once_with()
    wait_k8s.assert_called_once_with()
    assert len(stage1_calls) == 1
    assert len(stage2_calls) == 1
    first = stage1_calls[0]
    second = stage2_calls[0]
    assert "terraform" in first[0]
    assert "apply" in first
    assert "-target=module.gke" in first
    assert "-target=module.kserve" not in first
    assert "terraform" in second[0]
    assert "apply" in second
    assert all(not arg.startswith("-target=") for arg in second), second


def test_run_sync_meili_resolves_url_and_restores_env() -> None:
    class _Proc:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    calls: list[list[str]] = []

    def _fake_run(cmd: list[str], **_: object):
        calls.append(cmd)
        if cmd[:4] == ["gcloud", "auth", "print-identity-token"]:
            return _Proc("oidc-token\n")
        if cmd[:4] == ["gcloud", "secrets", "versions", "access"]:
            return _Proc("meili-key\n")
        raise AssertionError(f"unexpected command: {cmd}")

    with (
        patch.dict(
            "os.environ",
            {
                "PROJECT_ID": "mlops-test",
                "MEILI_SERVICE": "meili-search",
                "MEILI_PRESIGNED_ID_TOKEN": "previous-token",
            },
            clear=False,
        ),
        patch(
            "scripts.setup.deploy_all.cloud_run_url", return_value="https://meili.example.run.app"
        ),
        patch("scripts.setup.deploy_all.run", side_effect=_fake_run),
        patch("scripts.setup.deploy_all.sync_meili_run", return_value=5) as sync_mock,
    ):
        assert dall._run_sync_meili() == 0
        assert dall.os.environ["MEILI_PRESIGNED_ID_TOKEN"] == "previous-token"

    sync_mock.assert_called_once_with(
        [
            "--project-id=mlops-test",
            "--meili-base-url=https://meili.example.run.app",
            "--require-identity-token",
            "--api-key=meili-key",
        ]
    )
    assert calls == [
        ["gcloud", "auth", "print-identity-token"],
        [
            "gcloud",
            "secrets",
            "versions",
            "access",
            "latest",
            "--secret=meili-master-key",
            "--project=mlops-test",
        ],
    ]
