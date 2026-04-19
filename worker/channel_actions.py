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

안티디텍션: 각 단계 앞뒤로 human-like delay + 실패 시 조용히 로그.
"""
import random
from pathlib import Path

from hydra.browser.actions import random_delay, type_human
from hydra.core.logger import get_logger

log = get_logger("channel_actions")

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


async def rename_channel(page, channel_name: str) -> bool:
    """YouTube Studio 에서 채널 이름 변경. 이미 같은 이름이면 skip.

    YT Studio 의 Settings → Basic info 접근. 페이지 구조는 locale 따라 달라
    여러 셀렉터 시도.
    """
    if not channel_name:
        return False

    await page.goto("https://studio.youtube.com/channel/editing/basic",
                    wait_until="domcontentloaded")
    await random_delay(2.5, 4.5)

    try:
        name_input = page.locator(
            "input#text-input[aria-label*='이름'], input#given-name-input, "
            "#name-container input, #channel-name-input input"
        ).first
        await name_input.wait_for(timeout=10_000)
        current = (await name_input.input_value()) or ""
        if current.strip() == channel_name.strip():
            log.info(f"channel name already '{channel_name}' — skip")
            return True
        await name_input.click()
        # 전체 선택 후 덮어쓰기 (Mac/Win 차이 대응 — Control+a)
        try:
            await page.keyboard.press("Meta+a")
        except Exception:
            await page.keyboard.press("Control+a")
        await random_delay(0.2, 0.5)
        await page.keyboard.press("Backspace")
        await random_delay(0.3, 0.7)
        await type_human(
            page,
            "input#text-input, input#given-name-input, #name-container input, #channel-name-input input",
            channel_name,
        )
        await random_delay(1.0, 2.0)
    except Exception as e:
        log.warning(f"rename_channel failed at input step: {e}")
        return False

    # 게시/저장
    try:
        publish = page.locator(
            "button:has-text('게시'), button:has-text('Publish'), "
            "button:has-text('저장'), #publish-button"
        ).first
        await publish.click(timeout=5_000)
        await random_delay(2.0, 4.0)
    except Exception:
        pass

    log.info(f"channel renamed to '{channel_name}'")
    return True


async def set_description(page, description: str) -> bool:
    """채널 설명 설정 (비어있으면 pass)."""
    if not description:
        return False

    await page.goto("https://studio.youtube.com/channel/editing/basic",
                    wait_until="domcontentloaded")
    await random_delay(2.5, 4.5)

    try:
        desc_input = page.locator(
            "textarea[aria-label*='설명'], #description-container textarea, "
            "div#description-input textarea"
        ).first
        await desc_input.wait_for(timeout=10_000)
        await desc_input.click()
        try:
            await page.keyboard.press("Meta+a")
        except Exception:
            await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await random_delay(0.3, 0.7)
        await desc_input.type(description, delay=50)
        await random_delay(1.0, 2.0)
    except Exception as e:
        log.warning(f"set_description failed: {e}")
        return False

    try:
        publish = page.locator(
            "button:has-text('게시'), button:has-text('Publish'), "
            "button:has-text('저장')"
        ).first
        await publish.click(timeout=5_000)
        await random_delay(2.0, 4.0)
    except Exception:
        pass

    log.info(f"description set ({len(description)} chars)")
    return True


async def upload_avatar(page, avatar_path: str) -> bool:
    """프로필 사진 업로드. YT Studio → 맞춤설정 → 브랜딩 탭."""
    if not avatar_path or not Path(avatar_path).exists():
        log.warning(f"avatar file missing: {avatar_path}")
        return False

    # 브랜딩 탭 직접 URL
    await page.goto("https://studio.youtube.com/channel/editing/branding",
                    wait_until="domcontentloaded")
    await random_delay(3.0, 5.0)

    # 프로필 사진 섹션의 업로드 버튼
    try:
        upload_btn = page.locator(
            "button:has-text('업로드'), button:has-text('Upload'), "
            "#picture-section button, #avatar-section button"
        ).first
        await upload_btn.click(timeout=10_000)
        await random_delay(1.0, 2.0)
    except Exception as e:
        log.warning(f"upload button not found: {e}")
        return False

    try:
        file_input = page.locator("input[type='file']").first
        await file_input.set_input_files(avatar_path)
        await random_delay(4.0, 7.0)
    except Exception as e:
        log.warning(f"set_input_files failed: {e}")
        return False

    # 크롭 다이얼로그 → 완료 / 완료 버튼
    try:
        done = page.locator(
            "button:has-text('완료'), button:has-text('Done'), "
            "#done-button"
        ).first
        await done.click(timeout=8_000)
        await random_delay(2.0, 4.0)
    except Exception:
        pass

    # 게시
    try:
        publish = page.locator(
            "button:has-text('게시'), button:has-text('Publish')"
        ).first
        await publish.click(timeout=5_000)
        await random_delay(3.0, 5.0)
    except Exception:
        pass

    log.info(f"avatar uploaded from {avatar_path}")
    return True
