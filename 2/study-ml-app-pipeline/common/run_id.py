"""Run ID generator."""

import uuid
from datetime import datetime


def generate_run_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:6]
    return f"{ts}_{short_uuid}"
