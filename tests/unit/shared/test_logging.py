"""Structured logging configuration."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from ragassist.shared.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    structlog.reset_defaults()


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "nothing was logged"
    return lines[-1]


def test_json_output_is_one_valid_json_object_per_event(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    structlog.get_logger("svc").info("document_ingested", tenant="t1", chunks=3)

    record = json.loads(_last_line(capsys))
    assert record["event"] == "document_ingested"
    assert record["tenant"] == "t1" and record["chunks"] == 3
    assert record["level"] == "info"
    assert "timestamp" in record


def test_console_output_is_human_readable_not_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=False)
    structlog.get_logger("svc").info("hello")
    line = _last_line(capsys)
    assert "hello" in line
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


def test_level_filters_lower_severity_events(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", json_format=True)
    log = structlog.get_logger("svc")
    log.info("too_quiet")
    log.warning("loud_enough")
    out = capsys.readouterr().out
    assert "loud_enough" in out and "too_quiet" not in out


def test_calling_twice_does_not_duplicate_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    configure_logging("INFO", json_format=True)
    structlog.get_logger("svc").info("once")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert len(logging.getLogger().handlers) == 1


def test_json_records_do_not_leak_structlog_internals(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    structlog.get_logger("svc").info("clean")
    record = json.loads(_last_line(capsys))
    assert not {key for key in record if key.startswith("_")}, record.keys()


def test_unknown_level_name_falls_back_to_info(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("LOUD", json_format=True)
    assert logging.getLogger().level == logging.INFO


def test_standard_library_loggers_share_the_format(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    logging.getLogger("uvicorn.error").info("from stdlib")
    assert json.loads(_last_line(capsys))["event"] == "from stdlib"


def test_bound_context_is_included(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="req-42")
    try:
        structlog.get_logger("svc").info("with_context")
        assert json.loads(_last_line(capsys))["request_id"] == "req-42"
    finally:
        structlog.contextvars.clear_contextvars()
