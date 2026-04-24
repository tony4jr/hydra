"""Python logging → 서버 worker_errors 테이블 배치 전송.

설계:
- WARNING 이상 이벤트만 (volume 제어)
- 메모리 큐에 버퍼링 → 별도 스레드가 5초마다 배치 POST
- report-error 엔드포인트의 10분 dedupe 가 서버측 노이즈 흡수
- 전송 실패해도 워커 본체 흐름 영향 X (큐 drop 으로 그레이스풀 폴백)

사용법:
    from worker.log_shipper import install_log_shipping
    install_log_shipping(server_client)
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worker.client import ServerClient


_QUEUE_MAX = 200
_BATCH_INTERVAL = 5.0  # 초
_MIN_LEVEL = logging.WARNING


class ServerLogHandler(logging.Handler):
    """WARNING 이상을 내부 큐에 적재. 드롭 정책: 큐 꽉 차면 새 건 버림 (silent)."""

    def __init__(self, q: queue.Queue) -> None:
        super().__init__(level=_MIN_LEVEL)
        self._q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "kind": "task_fail" if record.levelno >= logging.ERROR else "other",
                "message": self.format(record)[:2000],
                "traceback": (
                    "".join(traceback.format_exception(*record.exc_info))
                    if record.exc_info else None
                ),
                "context": {
                    "logger": record.name,
                    "level": record.levelname,
                    "file": f"{record.pathname}:{record.lineno}",
                },
            }
            self._q.put_nowait(payload)
        except queue.Full:
            pass  # 드롭 — 본체 영향 방지
        except Exception:
            pass  # 로그 시스템이 워커를 죽이면 안 됨


class _Shipper(threading.Thread):
    """데몬 스레드 — 큐 비울 때까지 배치 POST."""

    def __init__(self, client: "ServerClient", q: queue.Queue) -> None:
        super().__init__(daemon=True, name="log-shipper")
        self._client = client
        self._q = q
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            time.sleep(_BATCH_INTERVAL)
            self._flush()

    def _flush(self) -> None:
        while not self._q.empty():
            try:
                item = self._q.get_nowait()
            except queue.Empty:
                return
            try:
                self._client.report_error(
                    kind=item["kind"],
                    message=item["message"],
                    traceback=item.get("traceback"),
                    context=item.get("context"),
                )
            except Exception:
                pass  # report_error 자체가 조용히 실패하도록 설계됐지만 한번 더 방어


def install_log_shipping(client: "ServerClient") -> None:
    """루트 로거에 핸들러 부착 + 백그라운드 shipper 시작 + sys.excepthook 도 덮어씀."""
    q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX)

    handler = ServerLogHandler(q)
    handler.setFormatter(logging.Formatter("%(name)s | %(message)s"))
    logging.getLogger().addHandler(handler)

    shipper = _Shipper(client, q)
    shipper.start()

    # 미처 잡히지 않은 예외 → 서버로 + 기존 동작도 유지
    orig_excepthook = sys.excepthook

    def _hook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        try:
            tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            client.report_error(
                kind="task_fail",
                message=f"uncaught {exc_type.__name__}: {exc_value}",
                traceback=tb_text,
                context={"source": "sys.excepthook"},
            )
        except Exception:
            pass
        orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
