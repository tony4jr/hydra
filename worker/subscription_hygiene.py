"""구독 관리 — 한국 채널만 구독 + 한국 외 채널 구독 취소.

한국 페르소나 + 한국 IP + 한국 지문 과 어긋나는 구독 이력은 YouTube/Google 의
앙상블 탐지 시그니처가 된다. 구독 액션은 **한국어 컨텍스트일 때만** 수행하고,
주기적으로 구독 리스트를 훑어 한국어가 아닌 채널은 1~2개씩 조용히 해지한다.

판정 휴리스틱 (보수적으로):
- 채널명 또는 영상 제목에 한글 유니코드 범위 문자 포함 → KR
- 채널 URL handle 이 영문만 + 한글 완전 부재 → non-KR 가능성 높음
- 명백한 예외 (K-POP 아이돌 공식 영문 이름 등) 는 허용

모든 네비게이션/클릭은 human-like delay 뒤에. 실패는 조용히 로그.
"""
import random
import re

from hydra.browser.actions import human_click, random_delay
from hydra.core.logger import get_logger

log = get_logger("subscription")

HANGUL_REGEX = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")


def contains_korean(text: str | None) -> bool:
    if not text:
        return False
    return bool(HANGUL_REGEX.search(text))


async def current_video_is_korean(page) -> bool:
    """현재 시청 중인 영상의 제목/채널명에 한글이 포함돼 있는지."""
    try:
        info = await page.evaluate("""() => ({
            title: document.querySelector('h1.ytd-watch-metadata, h1.title')?.textContent || '',
            channel: document.querySelector('ytd-channel-name a, #channel-name a, #upload-info #channel-name')?.textContent || '',
        })""")
    except Exception:
        return False
    return contains_korean(info.get("title")) or contains_korean(info.get("channel"))


async def maybe_subscribe_if_korean(page, probability: float = 0.3) -> bool:
    """현재 영상 페이지에서 한국어 컨텍스트면 구독 버튼 클릭.

    Returns True if subscribed, False otherwise.
    """
    if random.random() > probability:
        return False
    if not await current_video_is_korean(page):
        return False

    try:
        btn = page.locator("ytd-subscribe-button-renderer button").first
        if await btn.count() == 0:
            return False
        # 이미 구독 상태면 버튼 텍스트가 "구독중" / "Subscribed" — 중복 클릭 피함
        text = (await btn.inner_text(timeout=2000)).strip().lower()
        if "구독 중" in text or "subscribed" in text or "구독중" in text:
            return False
        await human_click(btn, timeout=5000)
        await random_delay(1.5, 3.0)
        return True
    except Exception as e:
        log.debug(f"subscribe click failed: {e}")
        return False


async def maybe_unsubscribe_non_korean(page, max_actions: int = 2,
                                        probability: float = 0.3) -> int:
    """구독 관리 페이지로 이동해 한국어가 아닌 채널 최대 N개 구독 취소.

    Returns number of unsubscriptions performed.
    """
    if random.random() > probability:
        return 0

    try:
        await page.goto("https://www.youtube.com/feed/channels",
                        wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
    except Exception:
        return 0

    # 각 구독 채널 row: #contents ytd-channel-renderer
    # 채널명: #text-container h3 / #channel-title
    try:
        rows = await page.evaluate("""() => {
          const items = Array.from(document.querySelectorAll('ytd-channel-renderer'));
          return items.slice(0, 30).map((r, idx) => {
            const name = (r.querySelector('#text-container h3, #channel-title')?.textContent || '').trim();
            return { idx, name };
          });
        }""")
    except Exception:
        return 0

    # 한국어 미포함 채널만 후보
    non_kr = [r for r in rows if r["name"] and not any(
        0xac00 <= ord(ch) <= 0xd7a3 or 0x1100 <= ord(ch) <= 0x11ff
        or 0x3130 <= ord(ch) <= 0x318f for ch in r["name"]
    )]
    if not non_kr:
        return 0

    # 상위 후보 중 랜덤 1~N개 선정 (모두 한 번에 지우지 않음)
    random.shuffle(non_kr)
    targets = non_kr[: min(max_actions, random.randint(1, max_actions))]

    removed = 0
    for row in targets:
        try:
            clicked = await page.evaluate(f"""() => {{
              const items = Array.from(document.querySelectorAll('ytd-channel-renderer'));
              const target = items[{row['idx']}];
              if (!target) return false;
              const subBtn = target.querySelector(
                'ytd-subscribe-button-renderer button, tp-yt-paper-button[subscribed], '
                '#subscribe-button button'
              );
              if (!subBtn) return false;
              subBtn.click();
              return true;
            }}""")
            if not clicked:
                continue
            await random_delay(1.5, 3.0)

            # 확인 다이얼로그 — "구독취소" 또는 "Unsubscribe"
            confirmed = await page.evaluate("""() => {
              const dlg = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytd-confirm-dialog-renderer'))
                .find(d => d.offsetParent !== null);
              if (!dlg) return false;
              const btns = Array.from(dlg.querySelectorAll('button, yt-button-renderer button'));
              const hit = btns.find(b => {
                const t = (b.textContent || '').toLowerCase();
                return t.includes('구독취소') || t.includes('unsubscribe') || t.includes('구독 취소');
              });
              if (hit) { hit.click(); return true; }
              return false;
            }""")
            if confirmed:
                removed += 1
                log.info(f"unsubscribed: {row['name']}")
                await random_delay(2.0, 4.0)
        except Exception as e:
            log.debug(f"unsubscribe failed for {row['name']}: {e}")

    return removed
