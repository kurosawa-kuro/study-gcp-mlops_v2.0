"""Run ID generation: YYYYMMDDTHHMMSSZ-<uuid8>."""

import uuid
from datetime import datetime, timezone


def generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}-{uuid.uuid4().hex[:8]}"
