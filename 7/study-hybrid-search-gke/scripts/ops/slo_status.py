"""Report current burn-rate and compliance of the Phase 6 search-api SLOs.

Queries the Cloud Monitoring REST API for the two SLOs created by
``infra/terraform/modules/slo`` (availability + latency) and prints a
compact summary — current compliance, error-budget remaining, and the
1h / 3d burn rates used by the fast/slow alert policies.

Resolves SLO resource names from Terraform outputs so operators do not
need to hand-type long ``projects/.../services/.../serviceLevelObjectives/...``
paths. Falls back to deterministic defaults if ``terraform output`` is not
reachable (e.g. from CI without tfstate access), matching the service_id
convention ``<service_name>-<service_id_suffix>`` in the SLO module.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess

from scripts._common import env, fail, gcloud, http_json


def _terraform_output(name: str) -> str:
    """Read a Terraform output from environments/dev. Empty string on failure.

    Intentionally silent on failure: operators may run this script without
    write access to tfstate (e.g. on another machine) and still want the
    fallback resource-name resolution to kick in.
    """
    try:
        proc = subprocess.run(
            ["terraform", "output", "-raw", name],
            cwd="infra/terraform/environments/dev",
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return proc.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _default_service_id(service_name: str, suffix: str) -> str:
    return f"{service_name}-{suffix}"


def _describe_slo(project_id: str, slo_name: str, token: str) -> dict:
    url = f"https://monitoring.googleapis.com/v3/{slo_name}?view=FULL"
    status, body = http_json("GET", url, token=token)
    if status != 200:
        raise RuntimeError(f"describe SLO failed HTTP {status}: {body}")
    return json.loads(body)


def _burn_rate(project_id: str, slo_name: str, window_seconds: int, token: str) -> float | None:
    """Fetch the most recent burn-rate sample via Monitoring timeSeries API.

    Uses select_slo_burn_rate() which is the same MQL function the alert
    policies key off. Returns None if there is no datapoint yet (freshly
    created SLO).
    """
    now = dt.datetime.now(tz=dt.timezone.utc)
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (now - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    filter_str = f'select_slo_burn_rate("{slo_name}", "{window_seconds}s")'
    url = (
        f"https://monitoring.googleapis.com/v3/projects/{project_id}/timeSeries"
        f"?filter={filter_str}"
        f"&interval.startTime={start}&interval.endTime={end}"
    )
    status, body = http_json("GET", url, token=token)
    if status != 200:
        raise RuntimeError(f"burn_rate lookup failed HTTP {status}: {body}")
    doc = json.loads(body)
    series = doc.get("timeSeries") or []
    if not series:
        return None
    points = series[0].get("points") or []
    if not points:
        return None
    value = points[0].get("value", {})
    return float(value.get("doubleValue", 0.0))


def main() -> int:
    project_id = env("PROJECT_ID")
    if not project_id:
        return fail("PROJECT_ID not set (env/config/setting.yaml or env var)")

    service_name = env("API_SERVICE", "search-api")
    suffix = env("SLO_SERVICE_ID_SUFFIX", "slo")
    service_id = _default_service_id(service_name, suffix)

    availability_name = _terraform_output("slo_availability_name") or (
        f"projects/{project_id}/services/{service_id}/serviceLevelObjectives/availability-0p990"
    )
    latency_name = _terraform_output("slo_latency_name") or (
        f"projects/{project_id}/services/{service_id}/serviceLevelObjectives/latency-500ms-0p950"
    )

    token = gcloud("auth", "print-access-token", capture=True)
    if not token:
        return fail("could not mint access token via `gcloud auth print-access-token`")

    for label, name in (("availability", availability_name), ("latency", latency_name)):
        try:
            slo = _describe_slo(project_id, name, token)
        except RuntimeError as exc:
            print(f"[{label}] describe failed: {exc}")
            continue
        goal = slo.get("goal")
        period = slo.get("rollingPeriod") or slo.get("calendarPeriod")
        display = slo.get("displayName")
        fast = _burn_rate(project_id, name, 3600, token)
        slow = _burn_rate(project_id, name, 259200, token)
        print(f"[{label}] {display}")
        print(f"  goal={goal}  window={period}")
        print(f"  burn_rate(1h)={fast if fast is not None else 'n/a'}")
        print(f"  burn_rate(3d)={slow if slow is not None else 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
