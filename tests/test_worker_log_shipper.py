"""worker.log_shipper — 로그 배치 전송 테스트."""
import logging
import queue
import time

import pytest

from worker.log_shipper import ServerLogHandler, install_log_shipping


class _CapturingClient:
    def __init__(self) -> None:
        self.reports: list[dict] = []

    def report_error(self, kind, message, traceback=None, context=None):
        self.reports.append({
            "kind": kind,
            "message": message,
            "traceback": traceback,
            "context": context,
        })


def test_handler_emits_warning_level_only():
    q: queue.Queue = queue.Queue()
    h = ServerLogHandler(q)
    logger = logging.getLogger("test.shipper.warn")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(h)

    logger.debug("debug msg")
    logger.info("info msg")
    logger.warning("warn msg")
    logger.error("err msg")

    collected = []
    while not q.empty():
        collected.append(q.get_nowait())

    msgs = [c["message"] for c in collected]
    assert "warn msg" in msgs
    assert "err msg" in msgs
    assert not any("debug msg" in m for m in msgs)
    assert not any("info msg" in m for m in msgs)


def test_handler_classifies_error_as_task_fail_and_warning_as_other():
    q: queue.Queue = queue.Queue()
    h = ServerLogHandler(q)
    logger = logging.getLogger("test.shipper.kind")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(h)

    logger.warning("warn")
    logger.error("err")

    items = [q.get_nowait(), q.get_nowait()]
    kinds = {c["kind"] for c in items}
    assert kinds == {"other", "task_fail"}


def test_install_log_shipping_sends_to_client_via_background_thread():
    client = _CapturingClient()
    install_log_shipping(client)  # type: ignore[arg-type]

    log = logging.getLogger("test.shipper.integration")
    log.error("integration error")

    # shipper 는 5초 주기. 여기선 7초 대기.
    deadline = time.time() + 7
    while time.time() < deadline:
        if any("integration error" in r["message"] for r in client.reports):
            break
        time.sleep(0.2)

    assert any("integration error" in r["message"] for r in client.reports), \
        f"no error shipped in 7s; reports={client.reports}"
