"""Google 계정 언어를 한국어로 맞추는 워밍업 서브스텝.

베트남어 기반 Gmail 처럼 로캘 불일치 계정이 한국 IP/지문과 묶여서 YouTube/
Google 에 노출되는 것을 막는다. 최초 로그인 직후 1회 실행하면 계정 전체가
한국어 UI 로 전환된다.

흐름:
1. `myaccount.google.com/language` 접속
2. `document.documentElement.lang` 이 이미 'ko*' 이면 조기 반환 (idempotent)
3. 기본 언어 편집 버튼 클릭 — 현재 언어와 무관한 구조 기반 셀렉터
4. 검색 입력에 "한국어" 입력
5. 첫 option 클릭 → 국가 목록에서 "대한민국" 클릭
6. Save 버튼 대기 (disabled → enabled) 후 클릭
7. 언어 전환 대기 후 `documentElement.lang` 재확인

모든 클릭/타이핑은 human-like delay 를 거친다.
"""

import asyncio
from playwright.async_api import Page

from hydra.browser.actions import random_delay, type_human
from hydra.core.logger import get_logger

log = get_logger("language_setup")

LANGUAGE_URL = "https://myaccount.google.com/language"
TARGET_LANG_PREFIX = "ko"
TARGET_LANG_NAME = "한국어"
TARGET_REGION_NAME = "대한민국"


async def _current_lang(page: Page) -> str:
    return await page.evaluate("document.documentElement.lang || ''")


async def ensure_korean_language(page: Page, timeout_ms: int = 30_000) -> bool:
    """계정 UI 언어가 한국어가 아니면 한국어(대한민국)로 전환.

    Args:
        page: 로그인된 상태의 Playwright Page.
        timeout_ms: 한 단계당 대기 상한.

    Returns:
        True  — 이미 한국어였거나 전환 성공.
        False — 전환 실패 (상세 이유는 로그).
    """
    await page.goto(LANGUAGE_URL, wait_until="domcontentloaded")
    await random_delay(2.0, 4.0)

    current = await _current_lang(page)
    if current.startswith(TARGET_LANG_PREFIX):
        log.info(f"Already Korean (lang={current}) — skipping")
        return True

    log.info(f"Current lang={current}, switching to ko-KR")

    # Step 1: 기본 언어 편집 버튼
    # aria-label 은 현재 UI 언어로 표기되지만 구조적으로 첫 jscontroller="O626Fe"
    # button (편집 아이콘) 이 primary language 편집 버튼. 없으면 대체로 첫 버튼.
    edit_clicked = await page.evaluate("""
        () => {
          const candidates = Array.from(document.querySelectorAll('button'));
          const edit = candidates.find(b => {
            const aria = (b.getAttribute('aria-label') || '').toLowerCase();
            return /edit|chỉnh|修改|修正|수정|редакт/i.test(aria)
                || b.querySelector('i.google-material-icons')?.textContent?.trim() === 'edit';
          });
          if (edit) { edit.click(); return true; }
          return false;
        }
    """)
    if not edit_clicked:
        log.error("Failed to find primary-language edit button")
        return False
    await random_delay(1.0, 2.0)

    # Step 2: 언어 검색 입력
    try:
        await page.locator("input#c1").wait_for(timeout=timeout_ms)
        await type_human(page, "input#c1", TARGET_LANG_NAME)
    except Exception as e:
        log.error(f"Search input not ready: {e}")
        return False
    await random_delay(0.8, 1.5)

    # Step 3: 첫 번째 option 클릭 (한국어)
    clicked_lang = await page.evaluate(f"""
        () => {{
          const opts = Array.from(document.querySelectorAll('[role="option"]'));
          const hit = opts.find(o => o.textContent.trim() === '{TARGET_LANG_NAME}');
          if (hit) {{ hit.click(); return true; }}
          return false;
        }}
    """)
    if not clicked_lang:
        log.error("Korean language option not found in listbox")
        return False
    await random_delay(1.0, 2.0)

    # Step 4: 지역 목록에서 "대한민국" 클릭
    clicked_region = await page.evaluate(f"""
        () => {{
          const opts = Array.from(document.querySelectorAll('[role="option"]'));
          const hit = opts.find(o => o.textContent.trim() === '{TARGET_REGION_NAME}');
          if (hit) {{ hit.click(); return true; }}
          return false;
        }}
    """)
    if not clicked_region:
        log.error(f"Region '{TARGET_REGION_NAME}' not found")
        return False
    await random_delay(0.8, 1.5)

    # Step 5: Save 버튼이 활성화될 때까지 기다렸다 클릭 (aria-label 은 locale 따라 다름)
    save_clicked = await _wait_and_click_save(page, timeout_ms=timeout_ms)
    if not save_clicked:
        log.error("Save button did not become clickable")
        return False

    # Step 6: 적용 대기 후 검증
    await random_delay(3.0, 5.0)
    final = await _current_lang(page)
    if final.startswith(TARGET_LANG_PREFIX):
        log.info(f"Language switched to {final}")
        return True

    log.error(f"Save clicked but lang still={final}")
    return False


async def _wait_and_click_save(page: Page, timeout_ms: int) -> bool:
    """대화상자 내 Save 버튼이 enabled 되기를 기다렸다가 클릭."""
    deadline = asyncio.get_event_loop().time() + (timeout_ms / 1000)
    while asyncio.get_event_loop().time() < deadline:
        clicked = await page.evaluate("""
            () => {
              const dialog = Array.from(document.querySelectorAll('[role="dialog"]'))
                .find(d => d.querySelector('button'));
              if (!dialog) return 'no_dialog';
              const btns = Array.from(dialog.querySelectorAll('button'));
              // Save 버튼은 대화상자에서 마지막에 enabled 되는 primary action.
              // locale 무관: enabled 이고 aria-label 이 길이 있는 마지막 버튼.
              const enabled = btns.filter(b => !b.disabled);
              if (enabled.length === 0) return 'none_enabled';
              const save = enabled[enabled.length - 1];
              save.click();
              return 'clicked';
            }
        """)
        if clicked == "clicked":
            return True
        await asyncio.sleep(0.5)
    return False
