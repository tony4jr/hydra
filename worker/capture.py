"""Phase 1 — UNKNOWN_SCREEN 캡처 helper.

silent failure 박멸의 운영 핵심. 모르는 화면 만나면 strip 없이 일괄 기록:
  screenshot + HTML + URL + title + screen_state + failure_taxonomy + reason.

worker_api 의 /api/workers/report-error-with-screenshot 를 활용 (기존 인프라).
worker_errors 테이블의 신규 컬럼 (Phase 1.2 alembic) 에 적재됨.

Why:
  - Playwright/AdsPower 한쪽이라도 죽으면 호출자는 진행 중단해야 함
  - 캡처 실패가 caller 실행을 막지 않도록 silent (warning log)
  - context 에 task_id/account_id/worker_id 자동 첨부 (있으면)
"""
from __future__ import annotations

import json
import traceback
from typing import Any

from hydra.core.logger import get_logger
from hydra.protocol.failure_taxonomy import FailureTaxonomy

log = get_logger("worker.capture")


async def capture_unknown_screen(
    page: Any,
    *,
    screen_state: str,
    taxonomy: FailureTaxonomy = FailureTaxonomy.PAGE_VARIANT,
    reason: str = "",
    client: Any = None,
    task_id: int | None = None,
    account_id: int | None = None,
    failed_selector: str | None = None,
) -> None:
    """Capture UNKNOWN_SCREEN evidence and report to server.

    Args:
        page: Playwright Page (must have screenshot/content/url/title coroutines)
        screen_state: 분류 라벨 (e.g. "POST_PASSWORD_UNKNOWN", "TRUST_DEVICE_PROMPT")
        taxonomy: FailureTaxonomy enum
        reason: 짧은 free-text (e.g. "no email input and no known url match")
        client: worker.client.ServerClient instance (없으면 log만)
        task_id / account_id: 컨텍스트 attach
        failed_selector: 실패한 selector 문자열 (있으면)
    """
    # Phase 3.3 — 캡처 전에 ScreenResolution lookup. 매치+핸들러 성공 시
    # 캡처/큐 진입 스킵 (학습 루프 닫기). 매치 안 되거나 핸들러 실패 시 캡처로 fallback.
    if client is not None and hasattr(client, "lookup_resolution"):
        try:
            url_for_lookup = ""
            title_for_lookup = ""
            try:
                url_for_lookup = page.url
            except Exception:
                pass
            try:
                title_for_lookup = await page.title()
            except Exception:
                pass
            res = client.lookup_resolution(
                screen_state=screen_state,
                url=url_for_lookup,
                title=title_for_lookup,
            )
            if res is not None:
                from worker.resolution import apply_resolution
                ok = await apply_resolution(page, res)
                if ok:
                    log.info(f"UNKNOWN_SCREEN resolved by resolution "
                             f"{res.get('resolution_id')} ({res.get('resolution_type')}) "
                             f"— capture skipped")
                    if account_id is not None and hasattr(client, "report_account_event"):
                        try:
                            client.report_account_event(
                                account_id=account_id,
                                event_type="other",
                                message=(f"resolution {res.get('resolution_id')} applied "
                                         f"({res.get('resolution_type')}) state={screen_state}"),
                                task_id=task_id,
                                screen_state=screen_state,
                                context={"resolution_id": res.get("resolution_id"),
                                         "resolution_type": res.get("resolution_type")},
                            )
                        except Exception:
                            pass
                    return
        except Exception as e:
            log.warning(f"resolution lookup raised: {type(e).__name__}: {e}")

    # 1) 페이지 상태 캡처 — 각각 try/except 로 부분 실패 허용
    try:
        screenshot_bytes = await page.screenshot(full_page=False)
    except Exception as e:
        log.warning(f"screenshot failed: {type(e).__name__}: {e}")
        screenshot_bytes = b""

    try:
        html = await page.content()
        # PII 보호 — 매우 큰 HTML 잘라 저장 (50KB)
        html_truncated = html[:50_000] if html else ""
    except Exception as e:
        log.warning(f"html capture failed: {type(e).__name__}: {e}")
        html_truncated = ""

    try:
        url = page.url
    except Exception:
        url = ""

    try:
        title = await page.title()
    except Exception:
        title = ""

    context = {
        "screen_state": screen_state,
        "failure_taxonomy": taxonomy.value,
        "reason": reason,
        "captured_url": url,
        "captured_title": title,
        "captured_html_snippet": html_truncated[:2000],  # context dict 안엔 짧게
        "task_id": task_id,
        "account_id": account_id,
        "failed_selector": failed_selector,
    }

    message = f"UNKNOWN_SCREEN state={screen_state} taxonomy={taxonomy.value} reason={reason[:200]}"
    log.warning(message + f" url={url[:120]}")

    if client is None:
        # 클라이언트 없으면 로컬 로그만 (테스트 환경)
        return

    # 2) 서버 업로드 — multipart screenshot + context JSON
    try:
        if screenshot_bytes:
            client.report_error_with_screenshot(
                kind="unknown_screen",
                message=message,
                screenshot_bytes=screenshot_bytes,
                traceback=None,
                context=context,
                filename=f"unknown_{screen_state}.png",
            )
        else:
            # 스크린샷 없어도 worker_errors 는 기록
            client.report_error(
                kind="unknown_screen",
                message=message,
                traceback=None,
                context=context,
            )
    except Exception as e:
        log.warning(f"capture upload failed: {type(e).__name__}: {e}")

    # Phase 3.2 — account timeline 도 1줄 append (계정 있을 때만, best-effort).
    if account_id is not None and hasattr(client, "report_account_event"):
        try:
            client.report_account_event(
                account_id=account_id,
                event_type="unknown_screen",
                message=message,
                task_id=task_id,
                screen_state=screen_state,
                failure_taxonomy=taxonomy.value,
                context={
                    "reason": reason[:200],
                    "captured_url": url[:200],
                    "captured_title": title[:200],
                    "failed_selector": failed_selector,
                },
            )
        except Exception as e:
            log.warning(f"account_event emit failed: {type(e).__name__}: {e}")
