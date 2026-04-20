"""Google 계정 프로필 조정 — display name + OTP 2FA 시크릿 등록.

**Why:** 채널 이름만 한국어로 바꿔도 Google 계정 프로필은 원본 언어(예: 베트남어)
로 남음. Google 자체 ML/보안 시스템이 계정↔채널 언어 불일치를 이상 신호로 활용
할 가능성 있어 일치시키는 편이 안전. 추가 인증 없이 바로 변경 가능.

**두 가지 작업**:
1. Display name (`/profile/name/edit`): YouTube/Gmail 등에서 공개 표시되는 이름
   - aria-labelledby 가 가리키는 라벨의 첫 줄이 "이름"/"성" 인 input 두 개 채우기
2. OTP Authenticator 시크릿 등록 (`/two-step-verification/authenticator`):
   - Google OTP 앱 연동으로 base32 시크릿 획득 → `pyotp` 로 코드 생성 가능
   - 2FA 활성화(최상단 배너 제거)에는 전화번호/패스키가 필요 — OTP 만으로 불가능
   - 시크릿은 등록되므로 Google 이 미래에 TOTP 챌린지 요구 시 대응 가능

**Legal name 은 다루지 않음** — 대부분의 계정은 Google Payments Center 에
등록된 legal name 이 애초에 없어 편집 페이지가 "문제가 발생했습니다" 에러로 뜸.
(일부만 있고 관리 비용이 커서 전부 skip 하기로 결정.)

**한국어 이름 분할**: 단순히 첫 글자 = 성, 나머지 = 이름. 2~3 char 한국 이름
대부분 커버. 드문 복성(남궁/사공 등)은 별도 처리하지 않음.
"""
import re

import pyotp

from hydra.browser.actions import human_click, random_delay
from hydra.core.logger import get_logger

log = get_logger("google_account")


def split_korean_name(full_name: str) -> tuple[str, str]:
    """한국 이름을 (성, 이름) 튜플로 분리. '이준호' → ('이', '준호')."""
    name = (full_name or "").strip()
    if not name:
        return "", ""
    return name[0], name[1:]


async def _dismiss_blocking_popups(page) -> None:
    """경고/확인 다이얼로그가 진행을 막으면 닫기 시도."""
    for txt in ("확인", "OK", "계속", "다음"):
        try:
            btn = page.locator(f"[role='dialog'] button:has-text('{txt}')").first
            if await btn.is_visible(timeout=1000):
                await human_click(btn, timeout=2000)
                await random_delay(0.5, 1.0)
        except Exception:
            pass


async def update_account_name(page, korean_full_name: str, password: str | None = None) -> bool:
    """Google 계정 display name 을 한국어로 교체.

    password 전달 시 Google 이 본인확인 비밀번호 챌린지 띄우면 자동 처리.
    Returns True if save succeeded.
    """
    if not korean_full_name:
        return False

    family, given = split_korean_name(korean_full_name)
    if not family or not given:
        log.warning(f"update_account_name: invalid name '{korean_full_name}'")
        return False

    try:
        await page.goto(
            "https://myaccount.google.com/profile/name/edit",
            wait_until="domcontentloaded",
        )
        await random_delay(2.5, 4.0)
        await _dismiss_blocking_popups(page)
        # Google 이 민감한 프로필 변경 전 비밀번호 재확인을 요구할 수 있음
        if password:
            await _maybe_fill_password_challenge(page, password)
    except Exception as e:
        log.warning(f"update_account_name: goto failed: {e}")
        return False

    # Google 이름 편집 폼 input 찾기. get_by_label("이름", exact=True) 은 Google 의
    # aria-labelledby 가 "이름\n이름\n이름" (라벨 텍스트 여러 번 join) 으로 resolve
    # 되어 실패함. 대신 aria-labelledby → 실제 label 요소의 첫 줄이 "이름"/"성" 인
    # input 을 직접 찾는 견고한 방식.
    async def _find_inputs():
        return await page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const result = {given: null, family: null};
            for (const i of inputs) {
                const aria = i.getAttribute('aria-label') || '';
                if (aria.includes('검색') || aria.includes('Search')) continue;
                const labelId = i.getAttribute('aria-labelledby');
                if (!labelId) continue;
                const lbl = document.getElementById(labelId);
                if (!lbl) continue;
                const first = (lbl.innerText||'').split('\\n')[0].trim();
                if (first === '이름' && !result.given) result.given = i.id || '';
                if (first === '성' && !result.family) result.family = i.id || '';
            }
            return result;
        }""")

    try:
        # 최대 20초까지 대기하며 input id 획득
        import time
        deadline = time.time() + 20
        input_ids = {"given": None, "family": None}
        while time.time() < deadline:
            input_ids = await _find_inputs()
            if input_ids.get("given") and input_ids.get("family"):
                break
            await random_delay(0.5, 1.2)

        if not (input_ids.get("given") and input_ids.get("family")):
            # 페이지 리로드 후 재시도 (1회)
            log.info("update_account_name: inputs not found, reloading page")
            await page.reload(wait_until="domcontentloaded")
            await random_delay(3.0, 5.0)
            deadline = time.time() + 15
            while time.time() < deadline:
                input_ids = await _find_inputs()
                if input_ids.get("given") and input_ids.get("family"):
                    break
                await random_delay(0.5, 1.2)

        if not (input_ids.get("given") and input_ids.get("family")):
            log.warning(f"update_account_name: name inputs not found: {input_ids}")
            return False

        given_input = page.locator(f"#{input_ids['given']}")
        family_input = page.locator(f"#{input_ids['family']}")

        current_given = (await given_input.input_value()) or ""
        current_family = (await family_input.input_value()) or ""
        if current_given.strip() == given and current_family.strip() == family:
            log.info(f"account name already '{family} {given}' — skip")
            return True

        # JS 네이티브 setter + input 이벤트 dispatch (YT Studio 와 동일 이슈: React/
        # 웹컴포넌트 state 가 keyboard 입력으로 갱신 안 될 수 있어 DOM 직접 조작).
        set_js = """(el, v) => {
            const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;
            setter.call(el, v);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        }"""
        await family_input.evaluate(set_js, family)
        await random_delay(0.3, 0.6)
        await given_input.evaluate(set_js, given)
        await random_delay(0.5, 1.0)

        # 검증
        actual_family = (await family_input.input_value()) or ""
        actual_given = (await given_input.input_value()) or ""
        if actual_family.strip() != family or actual_given.strip() != given:
            log.warning(
                f"update_account_name: value mismatch after set — "
                f"wanted '{family}/{given}' actual '{actual_family}/{actual_given}'"
            )
            return False
    except Exception as e:
        log.warning(f"update_account_name: fill failed: {e}")
        return False

    # 저장 버튼 클릭
    try:
        save_btn = page.locator(
            "button:has-text('저장'), button:has-text('Save')"
        ).first
        await human_click(save_btn, timeout=5_000)
        await random_delay(2.0, 4.0)
    except Exception as e:
        log.warning(f"update_account_name: save click failed: {e}")
        return False

    # 저장 성공 확인 — URL 이 /profile/name (edit 제거) 또는 /personal-info 로 복귀
    try:
        await page.wait_for_url(
            re.compile(r"myaccount\.google\.com/(profile/name|personal-info)"),
            timeout=8_000,
        )
    except Exception:
        # URL 확인 실패해도 저장 자체는 됐을 수 있음 — 경고만 남기고 성공 처리
        log.warning("update_account_name: save confirmation URL not matched — assuming OK")

    log.info(f"account name updated to '{family} {given}'")
    return True


# ─── OTP Authenticator 등록 ──────────────────────────────────────────────

def _parse_secret_line(text: str) -> str | None:
    """`xxxx xxxx xxxx xxxx...` 형식 공백 구분 base32 추출 → 대문자 연속 문자열.

    Google 페이지는 lowercase + 4글자 단위 공백으로 표시. 공백 제거 후 대문자 변환.
    """
    m = re.search(r"(?:[a-z0-9]{4}\s+){3,7}[a-z0-9]{4}", text, flags=re.IGNORECASE)
    if not m:
        return None
    secret = m.group(0).replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z2-7]+", secret):
        return None
    return secret


async def _click_via_jsaction(page, span_text: str, timeout: int = 8_000) -> bool:
    """Google Material Design 버튼은 span 안의 텍스트 + 상위 래퍼의 jsaction 으로
    클릭 핸들러가 걸려있어 span.click() 으로는 반응 없음. xpath 로 상위 클릭 가능한
    요소를 찾아 Playwright click (실제 마우스 이벤트 발생)."""
    try:
        btn = page.locator(
            f"xpath=//span[normalize-space(text())='{span_text}']"
            f"/ancestor::*[contains(@jsaction,'click:')][1]"
        ).first
        await human_click(btn, timeout=timeout)
        return True
    except Exception as e:
        log.debug(f"jsaction click '{span_text}' failed: {e}")
        return False


async def register_otp_authenticator(page, password: str) -> tuple[str | None, bool]:
    """Google 계정에 OTP Authenticator 시크릿 등록.

    Returns: (secret, activated)
    - secret: base32 TOTP 시크릿 (성공 시). None 이면 등록 실패.
    - activated: 2FA 최종 활성화 성공 여부 (대부분 False — 전화번호 필요)

    등록만으로도 가치 있음:
    - DB 에 저장해 두고 향후 로그인 시 Google 이 TOTP 챌린지 요구하면 대응 가능
    - pyotp 로 6자리 코드 언제든 생성
    """
    if not password:
        log.warning("register_otp_authenticator: no password provided")
        return None, False

    # 1) 2FA 시작 페이지 → OTP 앱 추가
    try:
        await page.goto(
            "https://myaccount.google.com/signinoptions/twosv",
            wait_until="domcontentloaded",
        )
    except Exception as e:
        log.warning(f"otp: goto twosv failed: {e}")
        return None, False
    await random_delay(2.5, 4.0)

    # Google 이 비밀번호 재확인 요구 (2FA 설정 보안 체크)
    await _maybe_fill_password_challenge(page, password)

    # "OTP 앱 추가" 링크 클릭 → /two-step-verification/authenticator
    try:
        otp_link = page.locator("a:has-text('OTP 앱 추가'), a:has-text('OTP')").filter(
            has_text="OTP"
        ).first
        await human_click(otp_link, timeout=5_000)
    except Exception:
        # URL 로 직접 이동 (링크 없으면)
        await page.goto(
            "https://myaccount.google.com/two-step-verification/authenticator",
            wait_until="domcontentloaded",
        )
    await random_delay(2.5, 4.0)
    await _maybe_fill_password_challenge(page, password)

    # 2) "인증자 설정" 버튼 → QR 다이얼로그 → "스캔할 수 없나요?" 클릭 → 시크릿 노출
    try:
        setup_btn = page.locator("button:has-text('인증자 설정')").first
        await human_click(setup_btn, timeout=6_000)
    except Exception as e:
        log.warning(f"otp: 인증자 설정 button not found: {e}")
        return None, False
    await random_delay(2.5, 4.0)

    try:
        no_scan = page.locator("button:has-text('스캔할 수 없나요?'), a:has-text('스캔할 수 없나요?')").first
        await human_click(no_scan, timeout=5_000)
    except Exception as e:
        log.warning(f"otp: 스캔할 수 없나요 link not found: {e}")
        return None, False
    await random_delay(2.0, 3.5)

    # 시크릿 파싱
    try:
        body_text = await page.locator("body").inner_text(timeout=5_000)
    except Exception:
        body_text = ""
    secret = _parse_secret_line(body_text)
    if not secret:
        log.warning("otp: secret key not found in page text")
        return None, False
    log.info(f"otp: secret captured ({len(secret)} chars)")

    # 3) "다음" → 6자리 코드 입력 → "인증"
    try:
        # 다이얼로그 내부 "다음" (페이지에 여러 개 있을 수 있어 last 로 가시적인 것)
        next_btn = page.locator("tp-yt-paper-dialog button:has-text('다음'), button:has-text('다음')").last
        await human_click(next_btn, timeout=5_000)
    except Exception as e:
        log.warning(f"otp: 다음 (to code input) failed: {e}")
        return None, False
    await random_delay(2.0, 3.0)

    try:
        code = pyotp.TOTP(secret).now()
        code_input = page.locator("input[placeholder='코드 입력']").first
        await code_input.fill(code)
        await random_delay(0.5, 1.2)
        verify_btn = page.locator("button:has-text('인증')").last
        await human_click(verify_btn, timeout=5_000)
    except Exception as e:
        log.warning(f"otp: code entry/verify failed: {e}")
        return secret, False  # 시크릿은 이미 확보, 등록 실패로 처리
    await random_delay(3.0, 5.0)

    # 비밀번호 재확인이 또 뜰 수 있음
    await _maybe_fill_password_challenge(page, password)

    # 4) 2FA 최종 활성화 시도 (전화번호 없으면 실패 — 예상됨)
    activated = False
    try:
        await page.goto(
            "https://myaccount.google.com/signinoptions/twosv",
            wait_until="domcontentloaded",
        )
        await random_delay(2.5, 4.0)
        # "사용 설정" 버튼 클릭 (Material wrapper)
        if await _click_via_jsaction(page, "2단계 인증 사용 설정", timeout=6_000):
            await random_delay(3.0, 5.0)
            body_after = await page.locator("body").inner_text(timeout=3_000)
            # 활성화 성공 판정: "사용 중입니다" 또는 배너 없어짐
            if "사용 중" in body_after or "Turn off" in body_after or "사용 중지" in body_after:
                activated = True
            elif "전화번호 또는 패스키" in body_after or "전화번호를 추가" in body_after:
                log.info("otp: 2FA not activated — phone/passkey required")
    except Exception as e:
        log.debug(f"otp: activation attempt failed (expected for phoneless accounts): {e}")

    log.info(f"otp: registered secret, activated={activated}")
    return secret, activated


async def _maybe_fill_password_challenge(page, password: str) -> bool:
    """비밀번호 재확인 페이지 감지 시 자동 채우기. 없으면 무반응."""
    try:
        if "signin/challenge" not in page.url and "signin/pwd" not in page.url:
            # URL 로 감지 안 되는 경우 페이지 내 문구로 확인
            try:
                body = await page.locator("body").inner_text(timeout=1_500)
            except Exception:
                return False
            if "계속하려면 먼저 본인임을 인증" not in body and "비밀번호 입력" not in body:
                return False
        pwd_field = page.locator("input[type='password']").first
        if not await pwd_field.is_visible(timeout=2_000):
            return False
        await pwd_field.fill(password)
        await random_delay(0.5, 1.0)
        next_btn = page.locator("button:has-text('다음'), button:has-text('Next')").first
        await human_click(next_btn, timeout=5_000)
        await random_delay(3.5, 5.5)
        log.info("filled password challenge")
        return True
    except Exception as e:
        log.debug(f"password challenge skipped: {e}")
        return False
