"""911panel.us (NLTeam Mail Server) 임시 메일 조회 + Google 2FA 코드 추출.

911panel 은 인증 없이 이메일 주소만 입력하면 해당 인박스를 보여주는 임시 메일
서비스. HYDRA 계정들의 recovery_email 이 이 도메인을 쓰므로 Google 이 로그인
확인 코드를 그 주소로 보내면 여기서 읽어올 수 있다.

UI 흐름:
1. `https://911panel.us` 접속
2. `input#input-24` 에 email 입력
3. "Kiểm tra" 버튼 클릭 → `/email` 페이지
4. `div[role="option"].v-list-item` 리스트 중 최신 Google 인증 메일 클릭
5. body.innerText 에서 6자리 숫자 코드 추출

코드 도착 지연이 있으므로 최신 메일이 나타날 때까지 폴링.
"""

import asyncio
import re
from playwright.async_api import Page

from hydra.core.logger import get_logger

log = get_logger("mail_911panel")

INBOX_URL = "https://911panel.us"
CODE_REGEX = re.compile(r"\b(\d{6})\b")  # Google 2FA 는 6자리

# 최신 "Google 인증 코드" 메일을 찾기 위한 키워드 (제목에 포함될 가능성)
SUBJECT_KEYWORDS = [
    "인증 코드",      # ko
    "verification code",  # en
    "verification",
    "Cảnh báo bảo mật",   # vi — Google 보안 경고, 같은 메일에 코드 포함
    "security alert",
    "Google",
]


async def fetch_2fa_code(
    page: Page,
    recovery_email: str,
    *,
    wait_seconds: int = 90,
    poll_interval: float = 3.0,
    after_timestamp_ms: int | None = None,
) -> str | None:
    """911panel 인박스에서 최신 Google 2FA 6자리 코드를 추출.

    Args:
        page: 새 페이지(or 새 탭). 호출 후 이 페이지는 911panel 화면에 머물
            러 있음 — 필요시 호출자가 close 또는 navigate.
        recovery_email: 조회할 임시 메일 주소 (예: xxx@911panel.us).
        wait_seconds: 메일 도착을 기다리는 최대 시간.
        poll_interval: 리스트 재조회 간격.
        after_timestamp_ms: 이 시간 이후 도착한 메일만 인정 (optional).

    Returns:
        6자리 코드 문자열 또는 None (타임아웃).
    """
    await page.goto(INBOX_URL, wait_until="domcontentloaded")
    try:
        await page.locator("input#input-24").wait_for(timeout=10_000)
    except Exception:
        log.error("911panel: email input not ready")
        return None

    await page.locator("input#input-24").fill(recovery_email)
    # 폼 버튼은 1개 (검사 버튼)
    await page.locator("button").first.click()
    await asyncio.sleep(2)

    deadline = asyncio.get_event_loop().time() + wait_seconds
    seen_titles: set[str] = set()

    while asyncio.get_event_loop().time() < deadline:
        # 메시지 리스트에서 Google 관련 최신 메일 찾기
        target_found = await page.evaluate(f"""
            (keywords) => {{
              const items = Array.from(document.querySelectorAll('div[role="option"].v-list-item'));
              const target = items.find(el => {{
                const t = (el.textContent || '').toLowerCase();
                return keywords.some(k => t.includes(k.toLowerCase()));
              }});
              if (target) {{
                target.click();
                return true;
              }}
              return false;
            }}
        """, SUBJECT_KEYWORDS)

        if target_found:
            await asyncio.sleep(1.5)
            # 911panel 은 좌측 .col.col-4 에 리스트, 우측 .col.col-8 에 본문.
            # body.innerText 전체를 쓰면 옛 메일의 제목 (과거 코드 포함) 까지 섞여
            # 잘못된 코드를 뽑을 수 있으므로 본문 영역만 타겟한다.
            body_text = await page.evaluate(
                "document.querySelector('.col.col-8')?.innerText || ''"
            )
            matches = CODE_REGEX.findall(body_text)
            for code in matches:
                log.info(f"911panel: extracted code {code}")
                return code
            log.warning("Clicked message but no 6-digit code found in detail panel; waiting for new mail")

        await asyncio.sleep(poll_interval)
        # 인박스 refresh — 최상단에 "INBOX" 섹션을 다시 그리도록
        try:
            # 검사 버튼 재클릭 (리스트 갱신)
            await page.locator("button").first.click()
        except Exception:
            pass
        await asyncio.sleep(1)

    log.error(f"911panel: timeout waiting for code at {recovery_email}")
    return None
