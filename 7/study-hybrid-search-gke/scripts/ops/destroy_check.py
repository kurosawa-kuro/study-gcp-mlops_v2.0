"""Check for residual high-cost GCP resources after ``make destroy-all``.

This script is intentionally stdlib-only and shell-thin so it can be called
from Make. It distinguishes between:

- ``FAIL``: Phase 7 resources that should have been removed by destroy-all.
- ``WARN``: Google-managed residual buckets/repos that usually remain and
  cost little, but are still worth knowing about.
- ``ERROR``: the checker itself could not verify a resource group.

Exit code:
- 0: no FAIL / ERROR findings
- 1: at least one FAIL or ERROR finding exists
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass

from scripts._common import env, fail

HIGH_COST_BUCKET_SUFFIXES = ("models", "artifacts", "pipeline-root", "meili-data")
HIGH_COST_DATASETS = ("feature_mart", "mlops", "predictions")
ALLOWED_BUCKET_NAMES = ("tfstate", "vertex")
ALLOWED_BUCKET_PREFIXES = ("gcf-v2-sources-", "cloud-ai-platform-")
ALLOWED_BUCKET_SUFFIX_LITERALS = ("_cloudbuild",)
ALLOWED_ARTIFACT_REPOS = {"gcf-artifacts"}
API_DISABLED_MARKERS = (
    "SERVICE_DISABLED",
    "API has not been used in project",
    "has not been used in project",
    "is not enabled for the project",
    "has not been used or is disabled",
)


@dataclass(frozen=True)
class Finding:
    label: str
    severity: str
    items: tuple[str, ...]
    note: str = ""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check residual high-cost GCP resources after destroy-all."
    )
    parser.add_argument("--project-id", default=env("PROJECT_ID", "mlops-dev-a"))
    parser.add_argument("--region", default=env("REGION", "asia-northeast1"))
    parser.add_argument("--vertex-location", default=env("VERTEX_LOCATION", env("REGION")))
    parser.add_argument(
        "--json", action="store_true", help="Print a machine-readable JSON summary as well."
    )
    return parser.parse_args()


def _looks_like_api_disabled(stderr: str) -> bool:
    return any(marker in stderr for marker in API_DISABLED_MARKERS)


def _run_json(cmd: list[str]) -> tuple[list[dict], str | None]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if _looks_like_api_disabled(stderr):
            return [], None
        return [], stderr or f"command failed: {' '.join(cmd)}"
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return [], None
    payload = json.loads(stdout)
    if isinstance(payload, list):
        return payload, None
    if isinstance(payload, dict):
        return [payload], None
    return [], None


def _run_bq_json(cmd: list[str]) -> tuple[list[dict], str | None]:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if "Not found: Dataset" in stderr:
            return [], None
        if _looks_like_api_disabled(stderr):
            return [], None
        return [], stderr or f"command failed: {' '.join(cmd)}"
    stdout = (proc.stdout or "").strip()
    if not stdout:
        return [], None
    payload = json.loads(stdout)
    if isinstance(payload, list):
        return payload, None
    return [], None


def _pluck(rows: list[dict], key: str) -> tuple[str, ...]:
    values = []
    for row in rows:
        value = row.get(key)
        if value:
            values.append(str(value))
    return tuple(sorted(values))


def _collect_gke_clusters(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        ["gcloud", "container", "clusters", "list", f"--project={project_id}", "--format=json"]
    )
    return _pluck(rows, "name"), error


def _collect_cloud_run_services(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "run",
            "services",
            "list",
            f"--project={project_id}",
            "--platform=managed",
            "--format=json",
        ]
    )
    return _pluck(rows, "serviceName"), error


def _collect_dataflow_jobs(project_id: str, region: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "dataflow",
            "jobs",
            "list",
            f"--project={project_id}",
            f"--region={region}",
            "--status=active",
            "--format=json",
        ]
    )
    return _pluck(rows, "name"), error


def _collect_vertex_endpoints(
    project_id: str, vertex_location: str
) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "ai",
            "endpoints",
            "list",
            f"--project={project_id}",
            f"--region={vertex_location}",
            "--format=json",
        ]
    )
    names = []
    for row in rows:
        display_name = row.get("displayName") or row.get("name")
        if display_name:
            names.append(str(display_name))
    return tuple(sorted(names)), error


def _collect_cloud_functions(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "functions",
            "list",
            f"--project={project_id}",
            "--v2",
            "--format=json",
        ]
    )
    return _pluck(rows, "name"), error


def _collect_eventarc_triggers(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        ["gcloud", "eventarc", "triggers", "list", f"--project={project_id}", "--format=json"]
    )
    return _pluck(rows, "name"), error


def _collect_pubsub_topics(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        ["gcloud", "pubsub", "topics", "list", f"--project={project_id}", "--format=json"]
    )
    names = []
    for row in rows:
        topic = str(row.get("name", ""))
        if topic:
            names.append(topic.rsplit("/", 1)[-1])
    return tuple(sorted(names)), error


def _collect_pubsub_subscriptions(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "pubsub",
            "subscriptions",
            "list",
            f"--project={project_id}",
            "--format=json",
        ]
    )
    names = []
    for row in rows:
        sub = str(row.get("name", ""))
        if sub:
            names.append(sub.rsplit("/", 1)[-1])
    return tuple(sorted(names)), error


def _collect_buckets(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        ["gcloud", "storage", "buckets", "list", f"--project={project_id}", "--format=json"]
    )
    return _pluck(rows, "name"), error


def _collect_artifact_repos(project_id: str, region: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_json(
        [
            "gcloud",
            "artifacts",
            "repositories",
            "list",
            f"--project={project_id}",
            f"--location={region}",
            "--format=json",
        ]
    )
    names = []
    for row in rows:
        repo = str(row.get("name", ""))
        if repo:
            names.append(repo.rsplit("/", 1)[-1])
    return tuple(sorted(names)), error


def _collect_bq_datasets(project_id: str) -> tuple[tuple[str, ...], str | None]:
    rows, error = _run_bq_json(["bq", f"--project_id={project_id}", "ls", "--format=prettyjson"])
    names = []
    for row in rows:
        dataset_ref = row.get("datasetReference") or {}
        dataset_id = dataset_ref.get("datasetId")
        if dataset_id:
            names.append(str(dataset_id))
    return tuple(sorted(names)), error


def _classify_bucket_names(
    project_id: str, buckets: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fail_items = []
    warn_items = []
    high_cost_buckets = {f"{project_id}-{suffix}" for suffix in HIGH_COST_BUCKET_SUFFIXES}
    allowed_exact = {f"{project_id}-{suffix}" for suffix in ALLOWED_BUCKET_NAMES}
    allowed_exact.update({f"{project_id}{suffix}" for suffix in ALLOWED_BUCKET_SUFFIX_LITERALS})
    for bucket in buckets:
        if bucket in high_cost_buckets:
            fail_items.append(bucket)
            continue
        if bucket in allowed_exact or bucket.startswith(ALLOWED_BUCKET_PREFIXES):
            warn_items.append(bucket)
    return tuple(sorted(fail_items)), tuple(sorted(warn_items))


def _classify_artifact_repos(repos: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fail_items = []
    warn_items = []
    for repo in repos:
        if repo in ALLOWED_ARTIFACT_REPOS:
            warn_items.append(repo)
        else:
            fail_items.append(repo)
    return tuple(sorted(fail_items)), tuple(sorted(warn_items))


def _filter_high_cost_datasets(datasets: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(name for name in datasets if name in HIGH_COST_DATASETS))


def _evaluate(label: str, items: tuple[str, ...], error: str | None) -> Finding:
    if error:
        return Finding(label=label, severity="ERROR", items=(), note=error)
    if items:
        return Finding(label=label, severity="FAIL", items=items)
    return Finding(label=label, severity="OK", items=())


def _render_text(findings: list[Finding]) -> None:
    for finding in findings:
        if finding.severity == "OK":
            print(f"[OK] {finding.label}")
            continue
        if finding.items:
            print(f"[{finding.severity}] {finding.label}: {', '.join(finding.items)}")
            continue
        print(f"[{finding.severity}] {finding.label}: {finding.note}")


def _render_json(findings: list[Finding]) -> None:
    payload = [
        {
            "label": finding.label,
            "severity": finding.severity,
            "items": list(finding.items),
            "note": finding.note,
        }
        for finding in findings
    ]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def collect_findings(*, project_id: str, region: str, vertex_location: str) -> list[Finding]:
    gke_clusters, gke_error = _collect_gke_clusters(project_id)
    cloud_run_services, cloud_run_error = _collect_cloud_run_services(project_id)
    dataflow_jobs, dataflow_error = _collect_dataflow_jobs(project_id, region)
    vertex_endpoints, vertex_error = _collect_vertex_endpoints(project_id, vertex_location)
    cloud_functions, functions_error = _collect_cloud_functions(project_id)
    eventarc_triggers, eventarc_error = _collect_eventarc_triggers(project_id)
    pubsub_topics, topics_error = _collect_pubsub_topics(project_id)
    pubsub_subscriptions, subscriptions_error = _collect_pubsub_subscriptions(project_id)
    buckets, buckets_error = _collect_buckets(project_id)
    artifact_repos, repos_error = _collect_artifact_repos(project_id, region)
    datasets, datasets_error = _collect_bq_datasets(project_id)

    fail_buckets, warn_buckets = _classify_bucket_names(project_id, buckets)
    fail_repos, warn_repos = _classify_artifact_repos(artifact_repos)
    fail_datasets = _filter_high_cost_datasets(datasets)

    findings = [
        _evaluate("GKE clusters", gke_clusters, gke_error),
        _evaluate("Cloud Run services", cloud_run_services, cloud_run_error),
        _evaluate("Dataflow active jobs", dataflow_jobs, dataflow_error),
        _evaluate("Vertex endpoints", vertex_endpoints, vertex_error),
        _evaluate("Cloud Functions gen2", cloud_functions, functions_error),
        _evaluate("Eventarc triggers", eventarc_triggers, eventarc_error),
        _evaluate("Pub/Sub topics", pubsub_topics, topics_error),
        _evaluate("Pub/Sub subscriptions", pubsub_subscriptions, subscriptions_error),
        _evaluate("Phase 7 high-cost buckets", fail_buckets, buckets_error),
        _evaluate("Artifact Registry repositories", fail_repos, repos_error),
        _evaluate("Phase 7 BigQuery datasets", fail_datasets, datasets_error),
    ]
    if warn_buckets:
        findings.append(
            Finding(
                label="Managed residual buckets",
                severity="WARN",
                items=warn_buckets,
                note="Google-managed or intentionally preserved buckets",
            )
        )
    if warn_repos:
        findings.append(
            Finding(
                label="Managed residual Artifact Registry repositories",
                severity="WARN",
                items=warn_repos,
                note="Google-managed repository",
            )
        )
    return findings


def main() -> int:
    args = _parse_args()
    findings = collect_findings(
        project_id=args.project_id,
        region=args.region,
        vertex_location=args.vertex_location,
    )

    _render_text(findings)
    if args.json:
        _render_json(findings)

    bad = [finding for finding in findings if finding.severity in {"FAIL", "ERROR"}]
    if bad:
        return fail(f"destroy-check failed: {len(bad)} problematic finding(s)")
    print("destroy-check passed: no high-cost residual Phase 7 resources found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
