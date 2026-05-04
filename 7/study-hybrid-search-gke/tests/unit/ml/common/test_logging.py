import json
import logging

from ml.common.logging import CloudLoggingJsonFormatter


def test_json_formatter_basic() -> None:
    fmt = CloudLoggingJsonFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    payload = json.loads(fmt.format(record))
    assert payload["severity"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["logger"] == "x"
    assert "time" in payload


def test_json_formatter_extras() -> None:
    fmt = CloudLoggingJsonFormatter()
    record = logging.LogRecord(
        name="x",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="m",
        args=(),
        exc_info=None,
    )
    record.extras = {"request_id": "abc", "n": 5}
    payload = json.loads(fmt.format(record))
    assert payload["request_id"] == "abc"
    assert payload["n"] == 5
