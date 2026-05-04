"""Shared diagnostics for Pub/Sub publisher adapters.

Phase 6 Run 1 で ranking-log topic の ``pubsub.publisher`` 権限欠落 (Terraform
state と GCP 側の非対称 drift) で /search が 500 を返す事故が発生。Cloud
Logging のデフォルト ``PermissionDenied`` だけでは「どの topic / どの SA / 第二・
第三候補は何か」が読み取れず復旧に時間を食ったので、publish 時点で root-cause
候補を並べて記録するヘルパを共通化した。

Phase B-2 で ``adapters/candidate_retriever.py`` から `pubsub_*_publisher.py`
を file 分割した際に、これらのヘルパだけを切り出して両方の adapter から再利用
できるようにした。
"""

from __future__ import annotations

import logging
import os

from google.api_core import exceptions as google_exceptions

logger = logging.getLogger("app.pubsub_publisher")


def runtime_sa_hint() -> str:
    """Best-effort identity label for the current worker (no auth round trip)."""
    return (
        os.getenv("K_SERVICE_ACCOUNT", "")
        or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        or os.getenv("CLOUD_RUN_SERVICE_ACCOUNT", "")
        or "<unknown-sa>"
    )


def log_publish_failure(
    *,
    where: str,
    topic_path: str,
    exc: BaseException,
) -> None:
    """Structured diagnostics for Pub/Sub publish failures.

    ranking-log / search-feedback / retrain-trigger 共通で使う。root cause
    候補を 1〜3 列挙して、現場 operator が Cloud Logging の 1 行で切り分け
    できるようにする。
    """
    hints: list[str]
    if isinstance(exc, google_exceptions.PermissionDenied):
        hints = [
            "H1: runtime SA (sa-api) に roles/pubsub.publisher が欠落 — "
            "`gcloud pubsub topics get-iam-policy <topic>` で確認、"
            "`terraform apply` で tfstate と GCP を再同期 (Phase 6 Run 1 の drift)",
            "H2: Pub/Sub API (pubsub.googleapis.com) が project で disable — "
            "`gcloud services list --enabled | grep pubsub`",
            "H3: topic が別 project に作られた / 名前ミスマッチ — "
            "topic_path をダンプして project 部分を確認",
        ]
    elif isinstance(exc, google_exceptions.NotFound):
        hints = [
            "H1: topic が存在しない (destroy-all の後など) — "
            "`gcloud pubsub topics list --project=<id>`",
            "H2: topic 名の typo (env `RANKING_LOG_TOPIC` / `FEEDBACK_TOPIC` / `RETRAIN_TOPIC`)",
            "H3: project id ミスマッチ (publisher_client は settings.project_id から topic_path 組み立て)",
        ]
    elif isinstance(exc, google_exceptions.DeadlineExceeded | TimeoutError):
        hints = [
            "H1: Pub/Sub API 側でスロットリング / 一時的な遅延",
            "H2: publisher client の batching 中にローカル timeout (.result(timeout=5) 固定)",
            "H3: Cloud Run 側で egress が詰まっている (VPC connector や outbound 制限)",
        ]
    else:
        hints = [
            "H1: 未分類の gRPC / network 例外 — exc.__class__ と grpc status を確認",
            "H2: payload JSON 化で非 ASCII / datetime 等の serialize 失敗 (直前の TypeError を探す)",
            "H3: pubsub_v1.PublisherClient の credentials 初期化失敗 (ADC 未設定)",
        ]
    logger.error(
        "pubsub.publish FAILED where=%s topic_path=%s sa_hint=%s exc_type=%s exc=%s hints=%s",
        where,
        topic_path,
        runtime_sa_hint(),
        type(exc).__name__,
        exc,
        " | ".join(hints),
    )


def as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
