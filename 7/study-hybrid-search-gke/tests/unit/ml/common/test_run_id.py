import re

from ml.common.utils import generate_run_id


def test_generate_run_id_format() -> None:
    rid = generate_run_id()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{8}", rid), rid


def test_generate_run_id_uniqueness() -> None:
    rids = {generate_run_id() for _ in range(50)}
    assert len(rids) == 50
