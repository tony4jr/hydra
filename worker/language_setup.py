"""Google 계정 언어를 한국어로 맞추는 워밍업 서브스텝.

베트남어 기반 Gmail 처럼 로캘 불일치 계정이 한국 IP/지문과 묶여서 YouTube/
Google 에 노출되는 것을 막는다. 최초 로그인 직후 1회 실행하면 계정 전체가
한국어 UI 로 전환된다.

흐름:
1. `myaccount.google.com/language` 접속
2. `document.documentElement.lang` 이 이미 'ko*' 이면 "기타 언어"만 정리하고 반환
3. 기본 언어 편집 버튼 클릭 — 현재 언어와 무관한 구조 기반 셀렉터
4. 검색 입력에 "한국어" 입력
5. 첫 option 클릭 → 국가 목록에서 "대한민국" 클릭
6. Save 버튼 대기 (disabled → enabled) 후 클릭
7. 언어 전환 대기 후 `documentElement.lang` 재확인
8. 언어 페이지 재진입 → "기타 언어" 에 남아있는 비-한국어 언어 모두 삭제
   (베트남어 원본 계정은 Google 이 자동으로 "나를 위해 추가됨" 표시로
   "Tiếng Việt" 을 기타 언어에 남김 → 안티디텍션 위해 제거)

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
        log.info(f"Already Korean (lang={current}) — checking 기타 언어 only")
        removed = await _delete_other_languages(page, timeout_ms=timeout_ms)
        if removed:
            log.info(f"Removed {removed} leftover languages from 기타 언어")
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
    # ID 는 Google 빌드마다 변함 (`#c1`, `#c3` 등). 편집 다이얼로그엔 text input 1개만
    # 있으므로 visible text input 중 첫 번째를 잡는다.
    search_sel = "tp-yt-paper-dialog input[type='text']:visible, [role='dialog'] input[type='text']:visible, input[type='text']:visible"
    try:
        # Playwright 의 :visible 은 지원 안 되므로 locator.first 로 조합
        search_inp = page.locator(
            "tp-yt-paper-dialog input[type='text'], [role='dialog'] input[type='text']"
        ).first
        await search_inp.wait_for(state="visible", timeout=timeout_ms)
        # type_human 은 selector 문자열을 받으므로 고유한 것을 동적으로 id 로 잡음
        el_id = await search_inp.evaluate("el => el.id")
        if el_id:
            selector = f"input#{el_id}"
        else:
            selector = "tp-yt-paper-dialog input[type='text']"
        await type_human(page, selector, TARGET_LANG_NAME)
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
    if not final.startswith(TARGET_LANG_PREFIX):
        log.error(f"Save clicked but lang still={final}")
        return False
    log.info(f"Language switched to {final}")

    # Step 7: 기타 언어 섹션에서 자동 추가된 원본 언어 (Tiếng Việt 등) 삭제
    # Google 은 primary 변경 후 기존 언어를 "나를 위해 추가됨"으로 기타 언어에 남긴다.
    # 안티디텍션 원칙상 흔적 제거 — 재진입해야 업데이트된 DOM 이 보임.
    try:
        await page.goto(LANGUAGE_URL, wait_until="domcontentloaded")
        await random_delay(2.0, 4.0)
        removed = await _delete_other_languages(page, timeout_ms=timeout_ms)
        if removed:
            log.info(f"Removed {removed} leftover languages from 기타 언어")
    except Exception as e:
        log.warning(f"cleanup of 기타 언어 failed: {e}")

    return True


async def _delete_other_languages(page: Page, timeout_ms: int = 15_000) -> int:
    """"기타 언어" 섹션에 남아있는 비-한국어 언어 항목을 모두 삭제.

    Google 은 primary 변경 후 원래 언어를 "나를 위해 추가됨" 으로 기타 언어에
    자동 추가한다. 각 row 의 삭제 버튼 aria-label 은 `"{언어명} 삭제"` 패턴
    (locale 에 따라 "Remove {lang}" 등) 이지만 구조상 끝이 "삭제|Remove|Xóa"
    인 button 을 찾아 클릭. 확인 다이얼로그에서 primary action (보통 마지막
    enabled 버튼) 클릭. 여러 개 남아있을 수 있으니 루프.

    Returns: 삭제된 항목 수.
    """
    removed = 0
    max_iterations = 10  # 무한루프 방지

    for _ in range(max_iterations):
        # 현재 보이는 삭제 버튼 탐지 (한국어: "삭제", 영어: "Remove", 베트남어: "Xóa")
        has_target = await page.evaluate("""
            () => {
              const btns = Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent !== null);
              return btns.some(b => {
                const aria = b.getAttribute('aria-label') || '';
                return /삭제$|remove$|xóa$/i.test(aria);
              });
            }
        """)
        if not has_target:
            break

        # 첫 삭제 버튼 클릭
        clicked = await page.evaluate("""
            () => {
              const btns = Array.from(document.querySelectorAll('button'))
                .filter(b => b.offsetParent !== null);
              const hit = btns.find(b => {
                const aria = b.getAttribute('aria-label') || '';
                return /삭제$|remove$|xóa$/i.test(aria);
              });
              if (hit) { hit.click(); return hit.getAttribute('aria-label'); }
              return null;
            }
        """)
        if not clicked:
            break
        log.info(f"deleting other language: {clicked}")
        await random_delay(1.0, 2.0)

        # 확인 다이얼로그: 한국어 "제거", 영어 "Remove", 베트남어 "Xóa"
        # 다이얼로그 내 enabled 버튼 중 2번째(취소/제거 순) 또는 마지막 클릭
        confirmed = await page.evaluate("""
            () => {
              const dialog = Array.from(document.querySelectorAll('[role="dialog"], [role="alertdialog"]'))
                .find(d => d.offsetParent !== null);
              if (!dialog) return false;
              const btns = Array.from(dialog.querySelectorAll('button'))
                .filter(b => !b.disabled && b.textContent.trim());
              // primary destructive action 은 대체로 마지막
              const action = btns[btns.length - 1];
              if (action) { action.click(); return action.textContent.trim(); }
              return false;
            }
        """)
        if not confirmed:
            log.warning("confirmation dialog did not appear — aborting cleanup loop")
            break
        await random_delay(2.0, 4.0)
        removed += 1

    return removed


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
