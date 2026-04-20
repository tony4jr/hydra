"""YouTube Data Saver 모드 활성화 — 모바일 데이터 소비 절감.

폰 USB 테더링 / Wi-Fi 핫스팟으로 운영하는 Worker 에서 고해상도 스트리밍은
치명적. 144p 강제는 탐지 리스크 있으므로 실사용자도 흔히 쓰는 "Data Saver"
옵션을 대신 활성화한다 — YouTube 가 자동으로 480p 이하로 제한해 ~50% 절감.

UI 경로: YouTube 홈 → 오른쪽 상단 프로필 메뉴 → 설정 → "동영상 화질 환경설정"
또는 모바일 "데이터 세이버". Web 은 직접 URL `/account_playback` 로도 접근 가능.
"""
import random

from hydra.browser.actions import human_click, random_delay
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


async def set_primary_video_language(page, lang_display: str = "한국어") -> bool:
    """YouTube 기본 시청 언어 추가. 같은 /account_playback 페이지의 "언어" 섹션.

    Google 추천 엔진 / 자동 번역이 참조하는 사용자 언어 선호도. 한국 페르소나 계정
    은 '한국어' 를 기본 시청 언어로 지정하는 게 자연스러움. 이미 지정됐으면 skip.
    실패해도 치명적 아님 → 조용히 False.
    """
    try:
        await page.goto(
            "https://www.youtube.com/account_playback",
            wait_until="domcontentloaded",
        )
        await random_delay(2.5, 4.0)
    except Exception as e:
        log.debug(f"account_playback navigation failed: {e}")
        return False

    # "언어 추가 또는 수정" — a[role=button] 구조. 텍스트가 여러 줄에 걸쳐있어
    # locator has_text 로는 잡히지 않음 → JS 기반으로 클릭.
    try:
        opened = await page.evaluate("""() => {
          const el = Array.from(document.querySelectorAll('a[role="button"], a, button'))
            .find(n => (n.innerText||'').includes('언어 추가 또는 수정'));
          if (!el) return false;
          el.click();
          return true;
        }""")
        if not opened:
            log.debug("primary language edit link not found")
            return False
        await random_delay(2.0, 3.5)
    except Exception as e:
        log.debug(f"primary language edit link click failed: {e}")
        return False

    # 다이얼로그는 긴 스크롤 리스트 + 확인 버튼. 검색창 없음.
    # 대상 언어 row 를 scrollIntoView → label 클릭 (체크박스 토글).
    # 이미 체크돼있으면 '취소' 로 닫고 성공 리턴.
    try:
        state = await page.evaluate(
            """(target) => {
                const row = Array.from(document.querySelectorAll('yt-list-item-view-model'))
                    .find(r => (r.innerText||'').trim() === target);
                if (!row) return 'not_found';
                row.scrollIntoView({block: 'center'});
                const cb = row.querySelector('input[type="checkbox"]');
                if (cb && cb.checked) return 'already';
                const label = row.querySelector('label');
                if (label) label.click(); else row.click();
                return 'clicked';
            }""",
            lang_display,
        )
    except Exception as e:
        log.warning(f"primary language row select failed: {e}")
        return False

    if state == "not_found":
        log.debug(f"primary language row '{lang_display}' not in list")
        return False

    if state == "already":
        try:
            await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytd-popup-container, [role="dialog"]'))
                .filter(d => d.offsetParent !== null);
              for (const d of dlgs) {
                const btn = Array.from(d.querySelectorAll('button'))
                  .find(b => b.offsetParent !== null && (b.innerText||'').trim() === '취소');
                if (btn) { btn.click(); return; }
              }
            }""")
        except Exception:
            pass
        log.info(f"primary video language already '{lang_display}' — skip")
        return True

    await random_delay(0.8, 1.5)
    try:
        confirmed = await page.evaluate("""() => {
          const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytd-popup-container, [role="dialog"]'))
            .filter(d => d.offsetParent !== null);
          for (const d of dlgs) {
            const btn = Array.from(d.querySelectorAll('button'))
              .find(b => b.offsetParent !== null && (b.innerText||'').trim() === '확인');
            if (btn) { btn.click(); return true; }
          }
          return false;
        }""")
        if not confirmed:
            log.warning("primary language confirm button not found in dialog")
            return False
        await random_delay(2.0, 3.5)
    except Exception as e:
        log.warning(f"primary language confirm failed: {e}")
        return False

    log.info(f"primary video language set to '{lang_display}'")
    return True
