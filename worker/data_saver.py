"""YouTube Data Saver 모드 활성화 — 모바일 데이터 소비 절감.

폰 USB 테더링 / Wi-Fi 핫스팟으로 운영하는 Worker 에서 고해상도 스트리밍은
치명적. 144p 강제는 탐지 리스크 있으므로 실사용자도 흔히 쓰는 "Data Saver"
옵션을 대신 활성화한다 — YouTube 가 자동으로 480p 이하로 제한해 ~50% 절감.

UI 경로: YouTube 홈 → 오른쪽 상단 프로필 메뉴 → 설정 → "동영상 화질 환경설정"
또는 모바일 "데이터 세이버". Web 은 직접 URL `/account_playback` 로도 접근 가능.
"""
import random

from hydra.browser.actions import random_delay
from hydra.core.logger import get_logger

log = get_logger("data_saver")


async def enable_data_saver(page) -> bool:
    """YouTube Data Saver / 절약 모드 켜기. 이미 켜진 상태면 조용히 성공 반환.

    실패해도 치명적이지 않음 — 워밍업 본 플로우가 막히지 않도록 조용히 False.
    """
    try:
        await page.goto("https://www.youtube.com/account_playback",
                        wait_until="domcontentloaded")
        await random_delay(2.5, 4.5)
    except Exception as e:
        log.debug(f"account_playback navigation failed: {e}")
        return False

    # '동영상 화질 환경설정' 섹션 — 라디오: '자동 (권장)' / '데이터 세이버' / '고화질'
    # 일부 로캘에서 버튼 텍스트 변형 가능.
    try:
        clicked = await page.evaluate("""() => {
          // candidate labels in ko/en
          const labels = [
            '데이터 세이버', '데이터 절약', '데이터 절약 모드',
            'data saver', 'data-saver',
          ];
          // radio buttons + surrounding text blocks
          const radios = Array.from(document.querySelectorAll(
            'tp-yt-paper-radio-button, input[type=radio], [role=radio]'
          )).filter(el => el.offsetParent !== null);
          for (const r of radios) {
            const txt = (r.innerText || r.getAttribute('aria-label') || '').toLowerCase();
            const parentTxt = (r.parentElement?.innerText || '').toLowerCase();
            const combined = txt + ' ' + parentTxt;
            if (labels.some(l => combined.includes(l.toLowerCase()))) {
              // already checked?
              if (r.getAttribute('aria-checked') === 'true' || r.checked) return 'already';
              r.click();
              return 'clicked';
            }
          }
          return 'not_found';
        }""")
    except Exception as e:
        log.debug(f"data saver radio select failed: {e}")
        return False

    if clicked == "clicked":
        await random_delay(1.5, 3.0)
        log.info("Data saver enabled")
        return True
    if clicked == "already":
        log.info("Data saver already enabled — skip")
        return True
    log.debug("Data saver radio not found on page (locale/layout change?)")
    return False
