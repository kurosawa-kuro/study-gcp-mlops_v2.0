"""Resolve schedule specs for embed/train Vertex pipelines."""

from __future__ import annotations

import argparse
import json
from typing import Any

from scripts._common import env


def build_schedule_specs(target: str = "all") -> list[dict[str, Any]]:
    base_uri = env("PIPELINE_TEMPLATE_GCS_PATH")
    pipeline_root = env("PIPELINE_ROOT", f"gs://{env('PIPELINE_ROOT_BUCKET')}/runs")
    service_account = env("PIPELINE_SERVICE_ACCOUNT")
    specs = [
        {
            "name": "embed-pipeline-daily",
            "target": "embed",
            "template_uri": env(
                "EMBED_PIPELINE_TEMPLATE_URI",
                f"{base_uri.rstrip('/')}/property-search-embed.yaml",
            ),
            "pipeline_root": pipeline_root,
            "cron": env("EMBED_PIPELINE_SCHEDULE_CRON", "30 18 * * *"),
            "parameter_values": {"full_refresh": False},
            "service_account": service_account,
        },
        {
            "name": "train-pipeline-weekly",
            "target": "train",
            "template_uri": env(
                "TRAIN_PIPELINE_TEMPLATE_URI",
                f"{base_uri.rstrip('/')}/property-search-train.yaml",
            ),
            "pipeline_root": pipeline_root,
            "cron": env("TRAIN_PIPELINE_SCHEDULE_CRON", "0 19 * * 0"),
            "parameter_values": {},
            "service_account": service_account,
        },
    ]
    if target == "all":
        return specs
    return [spec for spec in specs if spec["target"] == target]


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve Vertex pipeline schedule specs")
    parser.add_argument("--target", choices=["all", "embed", "train"], default="all")
    args = parser.parse_args()
    print(json.dumps(build_schedule_specs(args.target), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
