"""YouTube Studio 채널 설정 액션 — 이름 / 아바타 / 설명.

**현재 호출 시점: 온보딩 세션의 마지막 단계** (`worker/onboard_session.py`).
과거 스펙에선 워밍업 Day N 에 스케줄되도록 `rename_at_warmup_day` /
`avatar_plan.set_at_warmup_day` 필드를 썼으나, 3일 워밍업 전제에 맞춰 지금은
온보딩 첫 세션에서 일괄 수행한다. channel_plan 의 위 두 필드는 정보 보존용
으로만 남아있고 실행 로직이 참조하지 않는다.

아바타 선택 규칙:
- channel_plan.avatar_policy == "set_during_warmup" 인 50% 계정만 업로드
- topic 이 'face' 면 성별/연령대 폴더에서 픽 (예: male/20s/m20_001.png)
- topic 이 object 이름이면 data/avatars/object/<topic>/ 에서 픽 (예: flower/flower_001.png)

URL/셀렉터 (2026-04 YT Studio UI 기준, shadow DOM 기반 커스텀 엘리먼트 사용):
- 진입: `https://studio.youtube.com/` → 리다이렉트된 URL 에서 채널 ID 추출
- 편집 페이지: `https://studio.youtube.com/channel/<ID>/editing/profile`
- 이름 입력: `ytcp-channel-editing-channel-name input` (아이디 없음, 커스텀 엘리먼트 wrapper)
- 아바타 업로드: `ytcp-profile-image-upload ytcp-button#upload-button button` → 파일 선택

안티디텍션: 각 단계 앞뒤로 human-like delay + 실패 시 조용히 로그.
"""
import re
import random
from pathlib import Path

from hydra.browser.actions import human_click, random_delay, type_human
from hydra.core.logger import get_logger

log = get_logger("channel_actions")


async def _resolve_channel_id(page) -> str | None:
    """Navigate to Studio root, extract channel ID from redirect URL.

    Returns None if the redirect didn't yield a /channel/UC... URL (e.g. login gone).
    """
    try:
        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
    except Exception as e:
        log.warning(f"channel_id: goto studio failed: {e}")
        return None
    await random_delay(2.0, 4.0)
    m = re.search(r"/channel/(UC[A-Za-z0-9_-]+)", page.url)
    return m.group(1) if m else None


async def _dismiss_studio_modals(page, max_rounds: int = 5) -> None:
    """YT Studio 첫 진입 시 뜨는 차단형 다이얼로그 닫기.

    YT Studio 의 첫 방문자 온보딩 위자드는 여러 단계 모달로 구성 — 한 번 닫아도
    다음 단계 모달이 뜰 수 있어 최대 max_rounds 회 반복.
    """
    modal_buttons = [
        "계속", "Continue",
        "시작하기", "Get started",
        "다음", "Next",
        "확인", "OK",
        "건너뛰기", "Skip",
    ]
    for _ in range(max_rounds):
        clicked_any = False
        for txt in modal_buttons:
            try:
                btn = page.locator(
                    f"tp-yt-paper-dialog ytcp-button:has-text('{txt}'), "
                    f"tp-yt-paper-dialog button:has-text('{txt}'), "
                    f"[role='dialog'] button:has-text('{txt}')"
                ).first
                if await btn.is_visible(timeout=1200):
                    await human_click(btn, timeout=3000)
                    await random_delay(1.0, 2.0)
                    log.info(f"dismissed studio modal via '{txt}'")
                    clicked_any = True
                    break  # restart loop — 이 모달 닫으면서 새 모달 뜰 수 있음
            except Exception:
                pass
        if not clicked_any:
            break  # 더 이상 닫을 모달 없음

AVATARS_ROOT = Path(__file__).resolve().parent.parent / "data" / "avatars"


def _age_folder(age: int) -> str:
    if age < 30: return "20s"
    if age < 40: return "30s"
    if age < 50: return "40s"
    if age < 60: return "50s"
    return "60s"


def pick_avatar_file(persona: dict, channel_plan: dict) -> str | None:
    """channel_plan 의 avatar_plan.topic 에 맞는 이미지 파일 경로 반환.
    없으면 None.
    """
    plan = channel_plan.get("avatar_plan") or {}
    topic = plan.get("topic")
    if not topic:
        return None

    if topic == "face":
        gender = persona.get("gender", "male")
        age = int(persona.get("age", 25))
        folder = AVATARS_ROOT / gender / _age_folder(age)
    else:
        folder = AVATARS_ROOT / "object" / topic

    if not folder.exists():
        log.warning(f"avatar folder missing: {folder}")
        return None

    files = sorted(p for p in folder.iterdir()
                   if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if not files:
        return None

    rng = random.Random(persona.get("slot_id", 0))
    return str(rng.choice(files))


async def rename_channel(page, channel_name: str, channel_id: str | None = None) -> bool:
    """YouTube Studio 에서 채널 이름 변경. 이미 같은 이름이면 skip.

    channel_id 를 받으면 편집 페이지로 직행. None 이면 자동 추출.
    """
    if not channel_name:
        return False

    if not channel_id:
        channel_id = await _resolve_channel_id(page)
        if not channel_id:
            log.warning("rename_channel: could not resolve channel_id")
            return False

    await page.goto(
        f"https://studio.youtube.com/channel/{channel_id}/editing/profile",
        wait_until="domcontentloaded",
    )
    await random_delay(2.5, 4.5)
    # 첫 진입 시 차단형 온보딩 모달이 뜰 수 있음 — 먼저 닫고 시작
    await _dismiss_studio_modals(page)

    try:
        # 현재 UI: ytcp-channel-editing-channel-name 커스텀 엘리먼트 내부 input
        # (id/aria 없음. 클래스는 빌드 해시라 불안정 → 상위 커스텀 태그로 스코프)
        name_input = page.locator("ytcp-channel-editing-channel-name input").first
        await name_input.wait_for(timeout=10_000)
        current = (await name_input.input_value()) or ""
        if current.strip() == channel_name.strip():
            log.info(f"channel name already '{channel_name}' — skip")
            return True

        # ⚠ YT Studio 의 channel-name input 은 Polymer 웹 컴포넌트. JS 네이티브
        # setter + input 이벤트 dispatch 로는 내부 dirty 플래그가 세팅되지 않아
        # publish 버튼이 disabled 로 남음 (값만 보이고 저장은 안 됨).
        #
        # 해결: 실제 키보드 이벤트 시퀀스 — triple-click 으로 전체 선택 → Delete
        # → keyboard.type 로 한 글자씩 입력. 각 키스트로크가 trusted 이벤트로
        # 컴포넌트 내부 state 를 업데이트 → dirty flag → publish 활성화.
        await name_input.click(click_count=3)
        await random_delay(0.2, 0.4)
        await page.keyboard.press("Delete")
        await random_delay(0.3, 0.6)
        # persona 타이핑 속도 반영. type_human 은 selector 기반이라 여기선
        # keyboard.type 으로 직접. delay 는 80~140ms (보통 사람 속도).
        await page.keyboard.type(channel_name, delay=random.randint(60, 140))
        await random_delay(0.6, 1.2)

        # 검증
        actual = (await name_input.input_value()) or ""
        if actual.strip() != channel_name.strip():
            log.warning(
                f"rename_channel: value mismatch after type — "
                f"wanted='{channel_name}' actual='{actual}'"
            )
            return False
    except Exception as e:
        log.warning(f"rename_channel failed at input step: {e}")
        return False

    # 게시 — publish 버튼 disabled 면 실패로 판정 (내부 state 미반영 의심).
    try:
        publish = page.locator("ytcp-button#publish-button button").first
        await publish.wait_for(timeout=5_000)
        disabled = await publish.get_attribute("disabled")
        aria_dis = await publish.get_attribute("aria-disabled")
        if disabled is not None or aria_dis == "true":
            log.warning(
                "rename_channel: publish button remains disabled after type — "
                "web component did not register change"
            )
            return False
        await human_click(publish, timeout=5_000)
        await random_delay(2.5, 4.5)
    except Exception as e:
        log.warning(f"rename_channel publish failed: {e}")
        return False

    log.info(f"channel renamed to '{channel_name}'")
    return True


async def set_description(page, description: str, channel_id: str | None = None) -> bool:
    """채널 설명 설정 (비어있으면 pass).

    2026-04 YT Studio 에서는 /editing/profile 탭에 설명 필드가 없음 — 기본정보 탭이
    더 이상 존재하지 않아 현재 경로로는 설정 불가. 현재는 graceful-skip (경고 1회 + False 리턴).
    추후 UI 에서 설명 입력 필드 경로 재확인 후 이 함수만 구현 교체.
    """
    if not description:
        return False
    log.warning("set_description: current YT Studio UI has no description field on /editing/profile — skipping")
    return False


async def upload_avatar(page, avatar_path: str, channel_id: str | None = None) -> bool:
    """프로필 사진 업로드. 프로필 탭의 ytcp-profile-image-upload 섹션 사용."""
    if not avatar_path or not Path(avatar_path).exists():
        log.warning(f"avatar file missing: {avatar_path}")
        return False

    if not channel_id:
        channel_id = await _resolve_channel_id(page)
        if not channel_id:
            log.warning("upload_avatar: could not resolve channel_id")
            return False

    await page.goto(
        f"https://studio.youtube.com/channel/{channel_id}/editing/profile",
        wait_until="domcontentloaded",
    )
    await random_delay(3.0, 5.0)
    await _dismiss_studio_modals(page)

    # 프로필 사진 섹션의 업로드 버튼 (배너/워터마크와 구분 — ytcp-profile-image-upload 로 스코프).
    # YT Studio 는 버튼 클릭 시 native file chooser 다이얼로그를 열므로 Playwright
    # expect_file_chooser 로 intercept (DOM input 직접 set_input_files 는 YT 의
    # lit-element 구조상 일관 동작 안 함).
    try:
        upload_btn = page.locator(
            "ytcp-profile-image-upload ytcp-button#upload-button button, "
            "ytcp-profile-image-upload button:has-text('업로드'), "
            "ytcp-profile-image-upload button:has-text('Upload')"
        ).first
        async with page.expect_file_chooser(timeout=10_000) as fc_info:
            await human_click(upload_btn, timeout=10_000)
        fc = await fc_info.value
        await fc.set_files(avatar_path)
        await random_delay(4.0, 7.0)
    except Exception as e:
        log.warning(f"avatar upload failed: {e}")
        return False

    # 크롭 다이얼로그 → 완료 / 완료 버튼
    try:
        done = page.locator(
            "button:has-text('완료'), button:has-text('Done'), "
            "#done-button"
        ).first
        await human_click(done, timeout=8_000)
        await random_delay(2.0, 4.0)
    except Exception:
        pass

    # 게시
    try:
        publish = page.locator(
            "ytcp-button#publish-button button, "
            "button:has-text('게시'), button:has-text('Publish')"
        ).first
        await human_click(publish, timeout=5_000)
        await random_delay(3.0, 5.0)
    except Exception:
        pass

    log.info(f"avatar uploaded from {avatar_path}")
    return True
