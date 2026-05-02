import io

import pytest

from harnas.log import Log
from harnas.tools.middleware import (
    RateLimitExceeded,
    RateLimiter,
    StaleReadError,
    StaleReadGuard,
    logged,
    retried,
    timed,
)


def test_logged_wraps_handler():
    trace = io.StringIO()
    handler = logged(lambda args: "ok", name="demo", io=trace)

    assert handler({"x": "y"}) == "ok"
    assert "[tool demo] call" in trace.getvalue()
    assert "[tool demo] ok" in trace.getvalue()


def test_retried_retries_matching_errors():
    attempts = 0

    def flaky(_args):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise RuntimeError("temporary")
        return "ok"

    handler = retried(flaky, attempts=3, backoff_ms=lambda _attempt: 0)

    assert handler({}) == "ok"
    assert attempts == 2


def test_rate_limiter_rejects_over_budget():
    limiter = RateLimiter(per_minute=1)
    handler = limiter.wrap(lambda _args: "ok")

    assert handler({}) == "ok"
    with pytest.raises(RateLimitExceeded):
        handler({})


def test_stale_read_guard_requires_fresh_read(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    log = Log()
    guard = StaleReadGuard(log=log, strict=True)
    read = guard.wrap_read(lambda args: path.read_text(encoding="utf-8"))
    edit = guard.wrap_edit(lambda args: path.write_text(args["text"], encoding="utf-8") or "ok")

    with pytest.raises(StaleReadError, match="never read"):
        edit({"path": str(path), "text": "hi"})

    assert read({"path": str(path)}) == "hello"
    path.write_text("changed", encoding="utf-8")

    with pytest.raises(StaleReadError, match="drifted"):
        edit({"path": str(path), "text": "fresh"})

    assert log[-1].type == "annotation"
    assert log[-1].payload["kind"] == "stale_read_guard.hash"


def test_timed_is_transparent():
    assert timed(lambda args: args["value"])({"value": "ok"}) == "ok"
