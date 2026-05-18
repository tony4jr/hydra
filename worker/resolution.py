"""Phase 3.3 — ScreenResolution apply handlers.

워커가 UNKNOWN 만나면:
  1. client.lookup_resolution() 호출 → 매치되면 dict
  2. apply_resolution(page, res) → 핸들러 실행. True = 처리됨 (캡처 스킵)

핸들러 한정 스코프 (이번 슬라이스):
  - auto_click_skip: action_config.selector 클릭. 가장 흔한 케이스 (trust device, "나중에" 버튼)

나머지 (auto_enter_code / retry_after_cooldown / fail_task / escalate_manual):
  매치는 되지만 핸들러는 별도 PR. 지금은 False 반환 → caller 가 캡처로 fallback.
"""
from __future__ import annotations

from typing import Any

from hydra.core.logger import get_logger

log = get_logger("worker.resolution")


async def apply_resolution(page: Any, resolution: dict) -> bool:
    """매치된 ScreenResolution 핸들러 실행.

    Args:
        page: Playwright Page
        resolution: lookup_resolution() 반환 dict

    Returns:
        True: 핸들러 성공 → caller 는 캡처 스킵
        False: 핸들러 미지원/실패 → caller 는 캡처 fallback
    """
    rtype = resolution.get("resolution_type")
    cfg = resolution.get("action_config") or {}

    if rtype == "auto_click_skip":
        selector = cfg.get("selector")
        if not selector:
            log.warning(f"auto_click_skip: missing selector in action_config")
            return False
        try:
            loc = page.locator(selector)
            await loc.first.click(timeout=cfg.get("timeout_ms", 5000))
            wait_sec = cfg.get("wait_sec")
            if wait_sec:
                import asyncio
                await asyncio.sleep(float(wait_sec))
            log.info(f"resolution {resolution.get('resolution_id')} applied "
                     f"(auto_click_skip selector={selector[:60]})")
            return True
        except Exception as e:
            log.warning(f"auto_click_skip failed selector={selector[:60]} "
                        f"err={type(e).__name__}: {e}")
            return False

    # 나머지 type 은 미지원 — 캡처로 fallback
    log.info(f"resolution {resolution.get('resolution_id')} type={rtype} "
             f"matched but handler not implemented — falling through to capture")
    return False
