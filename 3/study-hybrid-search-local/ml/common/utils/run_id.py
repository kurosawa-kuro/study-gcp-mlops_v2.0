"""Run ID generation: YYYYMMDDTHHMMSSZ-<uuid8>."""

import uuid
from datetime import UTC, datetime


def generate_run_id() -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"
