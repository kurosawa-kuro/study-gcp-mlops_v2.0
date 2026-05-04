"""Unit tests for scripts/deploy/configmap_overlay.py (FOS endpoint resolution)."""

from __future__ import annotations

import io
import json
import subprocess
from unittest.mock import patch

from scripts.deploy import configmap_overlay


def test_feature_online_store_public_domain_from_api_parses_rest_shape() -> None:
    """REST v1beta1 returns camelCase; must match feature_group / Terraform output source."""
    body = {
        "name": "projects/p/locations/asia-northeast1/featureOnlineStores/s",
        "dedicatedServingEndpoint": {
            "publicEndpointDomainName": "7.asia-northeast1-123.featurestore.vertexai.goog",
        },
    }
    fake_resp = io.BytesIO(json.dumps(body).encode())
    tok = subprocess.CompletedProcess(["gcloud"], returncode=0, stdout="tok\n")
    with (
        patch.object(configmap_overlay, "run", return_value=tok),
        patch.object(configmap_overlay.urllib.request, "urlopen", return_value=fake_resp),
    ):
        got = configmap_overlay._feature_online_store_public_domain_from_api(
            "p", "asia-northeast1", "s"
        )
    assert got == "7.asia-northeast1-123.featurestore.vertexai.goog"


def test_feature_online_store_public_domain_from_api_returns_empty_on_missing_domain() -> None:
    body = {"dedicatedServingEndpoint": {}}
    fake_resp = io.BytesIO(json.dumps(body).encode())
    tok = subprocess.CompletedProcess(["gcloud"], returncode=0, stdout="tok\n")
    with (
        patch.object(configmap_overlay, "run", return_value=tok),
        patch.object(configmap_overlay.urllib.request, "urlopen", return_value=fake_resp),
    ):
        got = configmap_overlay._feature_online_store_public_domain_from_api(
            "p", "asia-northeast1", "s"
        )
    assert got == ""
