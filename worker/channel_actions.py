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
import asyncio
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

    전략 변경 (2026-04): "계속" 같은 버튼 클릭은 다음 모달 연쇄를 유발해 복잡함 + 사이드바
    '팀 성장시키기' 툴팁도 안 사라짐. 대신 **모달 바깥 영역 slow-click (초당 2회)** 으로
    환영 모달만 닫고 → 페이지 reload 로 나머지 잔여 툴팁/iron-overlay 일괄 제거.

    상단 "2단계 인증 사용..." 경고 배너는 여기서 건드리지 않음 (x 버튼으로 따로 처리
    필요하면 호출자가).
    """
    # 1) "환영" 모달 처리 — 모달 바깥 1회 click 으로 닫힘. 다시 뜨면 또 클릭.
    for _ in range(max_rounds):
        has_welcome = False
        try:
            has_welcome = await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
                .filter(d => d.offsetParent !== null && (d.innerText||'').trim());
              return dlgs.some(d => {
                const t = (d.innerText||'');
                return t.includes('환영') || t.includes('Welcome') || t.includes('시작하기') || t.includes('Get started');
              });
            }""")
        except Exception:
            pass
        if not has_welcome:
            break
        try:
            # 모달 바깥 좌측 상단 (60, 300) — 안전 좌표. 1회 클릭.
            await page.mouse.click(60, 300, delay=random.randint(40, 100))
            log.info("studio: welcome dismissed (bg click)")
        except Exception:
            pass
        await random_delay(1.2, 2.0)

    # 2) "팀 성장시키기" 등 feature-discovery 툴팁 X 버튼 클릭 (여러 개 있을 수 있음)
    # 핵심 selector: ytcp-feature-discovery-callout 내부의 close-icon-button
    # (aria-label="닫기" / "Close"). 해상도 무관. 여러 툴팁 있을 수 있으니 루프.
    try:
        closed_count = await page.evaluate("""() => {
          let count = 0;
          // 1) 정확한 close-icon-button 매칭
          const closes = Array.from(document.querySelectorAll(
            'ytcp-feature-discovery-callout ytcp-icon-button.close-icon-button, ' +
            'ytcp-feature-discovery-callout button.close-icon-button'
          ));
          for (const c of closes) {
            const r = c.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) { c.click(); count++; }
          }
          // 2) aria-label 기반 fallback — callout 내 모든 icon button 중 닫기 라벨
          if (count === 0) {
            const btns = Array.from(document.querySelectorAll(
              'ytcp-feature-discovery-callout ytcp-icon-button, ' +
              'ytcp-feature-discovery-callout button'
            ));
            for (const b of btns) {
              const a = (b.getAttribute('aria-label') || '').toLowerCase();
              if (a === '닫기' || a === 'close' || a === 'dismiss') {
                const r = b.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) { b.click(); count++; }
              }
            }
          }
          return count;
        }""")
        if closed_count:
            log.info(f"studio: {closed_count} feature-discovery tooltip(s) closed")
            await random_delay(0.5, 1.0)
    except Exception:
        pass

    # 고아 backdrop 강제 제거 — 이후 input 클릭 가로막지 않게.
    try:
        await page.evaluate("""() => {
          document.querySelectorAll('tp-yt-iron-overlay-backdrop.opened, tp-yt-iron-overlay-backdrop[opened]')
            .forEach(b => b.remove());
        }""")
    except Exception:
        pass


async def _enter_customization(page) -> bool:
    """Studio 사이드바에서 '맞춤설정' 진입. 낮은 해상도면 항목이 접혀있어 scroll
    필요. 짧은 텍스트('설정') 오매칭 방지를 위해 exact-match + path 속성 우선.

    반환: /editing/profile 로 착지 확인 시 True.
    """
    try:
        await page.evaluate("""() => {
          const items = Array.from(document.querySelectorAll(
            'a, ytcp-navigation-drawer-entry'
          )).filter(n => n.offsetParent !== null);
          // 1) path 기반 우선 (YT 가 drawer entry 에 path 속성 부여)
          let hit = items.find(n => (n.getAttribute('path') || '').includes('editing'));
          // 2) 정확 텍스트 매칭 — trim 만, substring 말고
          if (!hit) hit = items.find(n => (n.innerText||'').trim() === '맞춤설정');
          // 3) aria-label 매칭
          if (!hit) hit = items.find(n => (n.getAttribute('aria-label') || '') === '맞춤설정');
          if (hit) {
            hit.scrollIntoView({block: 'center'});
            hit.click();
          }
        }""")
    except Exception:
        pass
    await random_delay(3.0, 5.0)
    return "editing" in page.url


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

    # 맞춤설정 페이지 진입 — `/editing/profile` 직접 goto 는 Studio 가 종종 대시보드로
    # 리다이렉트 시켜 버튼/input 이 로드되지 않음. 사이드바 '맞춤설정' 클릭이 안정적.
    try:
        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        await _dismiss_studio_modals(page)
        await _enter_customization(page)
    except Exception as e:
        log.warning(f"rename_channel: enter settings failed: {e}")
        return False

    try:
        # 현재 UI: ytcp-channel-editing-channel-name 커스텀 엘리먼트 내부 input
        # (id/aria 없음. 클래스는 빌드 해시라 불안정 → 상위 커스텀 태그로 스코프)
        name_input = page.locator("ytcp-channel-editing-channel-name input").first
        await name_input.wait_for(timeout=10_000)
        # 창이 작으면 이름 input 이 뷰포트 밖 — 스크롤로 노출
        try:
            await page.mouse.wheel(0, random.randint(200, 400))
            await random_delay(0.2, 0.5)
        except Exception:
            pass
        try:
            await name_input.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            pass
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
        await random_delay(2.0, 3.5)
    except Exception as e:
        log.warning(f"rename_channel publish failed: {e}")
        return False

    # 게시 확인 모달 — "이름 변경 확인" 등. 존재하면 확인 클릭.
    try:
        confirmed = await page.evaluate("""() => {
          const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
            .filter(d => d.offsetParent !== null);
          for (const d of dlgs) {
            const txt = (d.innerText||'').trim();
            if (!txt) continue;
            const btn = Array.from(d.querySelectorAll('button'))
              .find(b => b.offsetParent !== null && ['확인','OK','계속','게시'].includes((b.innerText||'').trim()));
            if (btn) { btn.click(); return 'clicked:' + (btn.innerText||'').trim(); }
          }
          return 'no_modal';
        }""")
        if confirmed.startswith("clicked:"):
            log.info(f"rename_channel: post-publish confirm {confirmed}")
            await random_delay(2.0, 3.5)
    except Exception:
        pass

    # 저장 검증 — publish 가 실제로 반영됐는지 체크. 최대 10초 폴링.
    # 성공 지표: 입력값이 새 이름 유지 AND publish 버튼 disabled (변경사항 없음 = 저장됨).
    saved = False
    for _ in range(10):
        try:
            cur = (await name_input.input_value()) or ""
            if cur.strip() != channel_name.strip():
                # 값이 되돌려짐 → 저장 실패
                break
            btn_dis = await publish.get_attribute("disabled")
            btn_aria = await publish.get_attribute("aria-disabled")
            if btn_dis is not None or btn_aria == "true":
                saved = True
                break
        except Exception:
            pass
        await random_delay(0.8, 1.2)

    if not saved:
        log.warning(
            f"rename_channel: publish did not persist — "
            f"final value='{(await name_input.input_value() or '')[:30]}'"
        )
        return False

    # 최종 검증 — reload 후 채널명이 기대 값 유지하는지 확인. 로컬 state 와
    # 서버 저장 간 괴리 방지 (publish 버튼이 disabled 가 되었어도 일부 케이스에서
    # 서버 커밋 실패 가능).
    try:
        await page.reload(wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        final_input = page.locator("ytcp-channel-editing-channel-name input").first
        await final_input.wait_for(timeout=10_000)
        final_val = (await final_input.input_value()) or ""
        if final_val.strip() != channel_name.strip():
            log.warning(
                f"rename_channel: reload verification FAILED — "
                f"wanted='{channel_name}' actual='{final_val[:40]}'"
            )
            return False
    except Exception as e:
        log.warning(f"rename_channel: reload verify error: {e}")
        # 리로드 자체 실패면 이전 saved 플래그로 신뢰 (관대 처리)

    log.info(f"channel renamed to '{channel_name}' (verified)")
    return True


async def change_handle(page, desired_handle: str, channel_id: str | None = None) -> bool:
    """YT 핸들(@handle) 변경.

    전략:
    1. 원본 핸들 입력
    2. 사용 가능하면 publish
    3. 불가하면 YT 가 페이지 내 추천 핸들 (ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor)
       을 제공 — 그 추천을 클릭해서 자동 입력 + publish

    (이전에 숫자 덧붙이는 fallback 은 추천 핸들 클릭 방식으로 대체)
    """
    if not desired_handle:
        return False

    if not channel_id:
        channel_id = await _resolve_channel_id(page)
        if not channel_id:
            log.warning("change_handle: could not resolve channel_id")
            return False

    # 맞춤설정 페이지 진입 — 사이드바 클릭이 가장 안정적
    try:
        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        await _dismiss_studio_modals(page)
        await _enter_customization(page)
    except Exception as e:
        log.warning(f"change_handle: enter settings failed: {e}")
        return False

    try:
        inp = page.locator("input[placeholder='핸들 설정']").first
        await inp.wait_for(timeout=10_000)
        # 창이 작으면 핸들 input 이 뷰포트 밖일 수 있음 — 스크롤로 노출 + 사람처럼
        # 위아래 살짝 휘적거려 '찾는 듯' 자연스럽게.
        try:
            await page.mouse.wheel(0, random.randint(300, 600))
            await random_delay(0.3, 0.7)
            await page.mouse.wheel(0, random.randint(-150, -50))
            await random_delay(0.2, 0.5)
        except Exception:
            pass
        try:
            await inp.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            pass
        current = (await inp.input_value()) or ""
        if current.strip() == desired_handle.strip():
            log.info(f"handle already '{desired_handle}' — skip")
            return True

        # 1차 시도: 원본 핸들 입력 + Enter (추천 anchor 렌더 트리거)
        # YT UI 는 입력만으론 validation 피드백이 즉시 안 올 때가 있어 Enter 를
        # 한 번 쳐야 "사용할 수 없는 핸들" + 추천 anchor 가 확실히 표시됨.
        await inp.click(click_count=3)
        await random_delay(0.15, 0.35)
        await page.keyboard.press("Delete")
        await random_delay(0.2, 0.4)
        await page.keyboard.type(desired_handle, delay=random.randint(60, 140))
        await random_delay(0.4, 0.8)
        try:
            await page.keyboard.press("Enter")
        except Exception:
            pass
        await random_delay(2.0, 3.0)

        pub = page.locator("ytcp-button#publish-button button").first
        pub_dis = await pub.get_attribute("disabled")
        pub_aria = await pub.get_attribute("aria-disabled")
        enabled = (pub_dis is None and pub_aria != "true")

        success_handle = None
        if enabled:
            success_handle = desired_handle
            log.info(f"change_handle: '{desired_handle}' available directly")
        else:
            # 추천 핸들 클릭 — YT 가 충돌 없는 variant 제시.
            # "사용할 수 없는 핸들" 판정 후 추천 anchor 가 렌더되는 데 수 초 추가
            # 소요될 수 있으므로 명시적으로 대기.
            try:
                await page.wait_for_selector(
                    'ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor',
                    timeout=8_000,
                )
            except Exception:
                pass
            suggested = await page.evaluate("""() => {
              const a = document.querySelector('ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor');
              if (!a) return null;
              const txt = (a.innerText||'').trim();
              a.click();
              return txt;
            }""")
            if not suggested:
                log.warning(
                    f"change_handle: '{desired_handle}' unavailable and no suggestion found"
                )
                return False
            await random_delay(1.2, 2.0)
            # 추천 핸들 클릭 후 input 값 = 추천값, publish 활성화 기대
            new_val = (await inp.input_value()) or ""
            pub_dis = await pub.get_attribute("disabled")
            pub_aria = await pub.get_attribute("aria-disabled")
            if (pub_dis is not None) or (pub_aria == "true"):
                log.warning(
                    f"change_handle: suggestion {suggested!r} clicked but publish still disabled"
                )
                return False
            success_handle = new_val or suggested.lstrip("@")
            log.info(f"change_handle: using suggested '{success_handle}'")

        # 게시
        try:
            await human_click(pub, timeout=5_000)
        except Exception:
            await pub.click(timeout=5_000)
        await random_delay(2.5, 4.0)

        # 확인 모달 처리
        try:
            await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
                .filter(d => d.offsetParent !== null && (d.innerText||'').trim());
              for (const d of dlgs) {
                const btn = Array.from(d.querySelectorAll('button'))
                  .find(b => b.offsetParent !== null && ['확인','게시','OK','저장'].includes((b.innerText||'').trim()));
                if (btn) btn.click();
              }
            }""")
            await random_delay(2.0, 3.5)
        except Exception:
            pass

        # Reload + 검증
        try:
            await page.reload(wait_until="domcontentloaded")
            await random_delay(3.0, 5.0)
            await _enter_customization(page)
            inp2 = page.locator("input[placeholder='핸들 설정']").first
            await inp2.wait_for(timeout=10_000)
            final = (await inp2.input_value()) or ""
            if final.strip() != success_handle.strip():
                log.warning(
                    f"change_handle: reload verification FAILED — "
                    f"wanted='{success_handle}' actual='{final}'"
                )
                return False
        except Exception as e:
            log.warning(f"change_handle reload verify error: {e}")

        log.info(f"handle changed to '{success_handle}' (verified)")
        return True

    except Exception as e:
        log.warning(f"change_handle failed: {e}")
        return False


async def set_channel_profile(
    page, channel_name: str, desired_handle: str,
    channel_id: str | None = None,
) -> tuple[bool, bool]:
    """이름 + 핸들 한 번에 수정 후 publish 1회.

    맞춤설정 페이지 진입 → 스크롤로 이름/핸들 input 노출 → 둘 다 변경 → publish.

    반환: (name_ok, handle_ok). publish 한 번으로 둘 다 서버 반영 시도.
    """
    if not channel_name or not desired_handle:
        return False, False

    if not channel_id:
        channel_id = await _resolve_channel_id(page)
        if not channel_id:
            log.warning("set_channel_profile: could not resolve channel_id")
            return False, False

    # 맞춤설정 진입
    try:
        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        await _dismiss_studio_modals(page)
        await _enter_customization(page)
    except Exception as e:
        log.warning(f"set_channel_profile: enter settings failed: {e}")
        return False, False

    name_input = page.locator("ytcp-channel-editing-channel-name input").first
    handle_input = page.locator("input[placeholder='핸들 설정']").first
    try:
        await name_input.wait_for(timeout=10_000)
        await handle_input.wait_for(timeout=10_000)
    except Exception as e:
        log.warning(f"set_channel_profile: inputs not visible: {e}")
        return False, False

    # 스크롤로 이름/핸들 노출 (해상도 낮을 때)
    try:
        await page.mouse.wheel(0, random.randint(300, 500))
        await random_delay(0.3, 0.7)
    except Exception:
        pass
    try:
        await handle_input.scroll_into_view_if_needed(timeout=5_000)
    except Exception:
        pass
    await random_delay(0.5, 1.0)

    # --- 이름 변경 ---
    cur_name = (await name_input.input_value()) or ""
    need_name = cur_name.strip() != channel_name.strip()
    if need_name:
        try:
            await name_input.scroll_into_view_if_needed(timeout=5_000)
            await name_input.click(click_count=3)
            await random_delay(0.2, 0.4)
            await page.keyboard.press("Delete")
            await random_delay(0.3, 0.6)
            await page.keyboard.type(channel_name, delay=random.randint(60, 140))
            await random_delay(0.6, 1.2)
            actual = (await name_input.input_value()) or ""
            if actual.strip() != channel_name.strip():
                log.warning(
                    f"set_channel_profile: name typed but value mismatch — "
                    f"wanted='{channel_name}' actual='{actual[:30]}'"
                )
                need_name = False  # 다음 단계 진행은 하되 name 은 실패로 처리
        except Exception as e:
            log.warning(f"set_channel_profile: name type err: {e}")
            need_name = False

    # --- 핸들 변경 ---
    cur_handle = (await handle_input.input_value()) or ""
    need_handle = not cur_handle.lower().startswith(desired_handle.lower())
    handle_success_val = None
    if need_handle:
        try:
            await handle_input.scroll_into_view_if_needed(timeout=5_000)
            await handle_input.click(click_count=3)
            await random_delay(0.2, 0.4)
            await page.keyboard.press("Delete")
            await random_delay(0.3, 0.6)
            await page.keyboard.type(desired_handle, delay=random.randint(60, 140))
            await random_delay(0.4, 0.8)
            # Enter 로 validation 유발 (추천 anchor 렌더)
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass
            await random_delay(2.0, 3.0)

            pub = page.locator("ytcp-button#publish-button button").first
            dis = await pub.get_attribute("disabled")
            aria_dis = await pub.get_attribute("aria-disabled")
            enabled = (dis is None and aria_dis != "true")

            if enabled:
                handle_success_val = desired_handle
            else:
                # 추천 anchor 대기 + 클릭
                try:
                    await page.wait_for_selector(
                        'ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor',
                        timeout=8_000,
                    )
                except Exception:
                    pass
                suggested = await page.evaluate("""() => {
                  const a = document.querySelector('ytcp-anchor.YtcpChannelEditingChannelHandleSuggestedHandleAnchor');
                  if (!a) return null;
                  const t = (a.innerText||'').trim();
                  a.click();
                  return t;
                }""")
                if not suggested:
                    log.warning("set_channel_profile: handle unavailable + no suggestion")
                else:
                    await random_delay(1.5, 2.5)
                    pub_dis = await pub.get_attribute("disabled")
                    pub_aria = await pub.get_attribute("aria-disabled")
                    if pub_dis is None and pub_aria != "true":
                        handle_success_val = (await handle_input.input_value()) or suggested.lstrip("@")
                    else:
                        log.warning(
                            f"set_channel_profile: suggestion {suggested!r} clicked but publish disabled"
                        )
        except Exception as e:
            log.warning(f"set_channel_profile: handle type err: {e}")

    # --- publish (1 번만) ---
    pub = page.locator("ytcp-button#publish-button button").first
    pub_dis = await pub.get_attribute("disabled")
    pub_aria = await pub.get_attribute("aria-disabled")
    if pub_dis is not None or pub_aria == "true":
        log.warning("set_channel_profile: publish still disabled — nothing to publish")
        # 이미 둘 다 타겟이면 publish 불필요. 검증 후 결과 반환.
    else:
        try:
            await human_click(pub, timeout=5_000)
        except Exception:
            await pub.click(timeout=5_000)
        await random_delay(2.5, 4.0)
        # 확인 모달 처리
        try:
            await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
                .filter(d => d.offsetParent !== null && (d.innerText||'').trim());
              for (const d of dlgs) {
                const btn = Array.from(d.querySelectorAll('button'))
                  .find(b => b.offsetParent !== null && ['확인','게시','OK','저장'].includes((b.innerText||'').trim()));
                if (btn) btn.click();
              }
            }""")
            await random_delay(2.0, 3.5)
        except Exception:
            pass

    # --- reload + 검증 ---
    name_ok = True
    handle_ok = True
    try:
        await page.reload(wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        await _enter_customization(page)
        final_name = (await page.locator("ytcp-channel-editing-channel-name input").first.input_value()) or ""
        final_handle = (await page.locator("input[placeholder='핸들 설정']").first.input_value()) or ""
        name_ok = final_name.strip() == channel_name.strip()
        handle_ok = final_handle.lower().startswith(desired_handle.lower())
        log.info(
            f"set_channel_profile verify: name={final_name!r} handle={final_handle!r} "
            f"name_ok={name_ok} handle_ok={handle_ok}"
        )
    except Exception as e:
        log.warning(f"set_channel_profile verify err: {e}")

    return name_ok, handle_ok


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

    # 맞춤설정 페이지 진입 — 사이드바 클릭 (직접 goto 는 대시보드 리다이렉트 위험)
    try:
        await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
        await random_delay(3.0, 5.0)
        await _dismiss_studio_modals(page)
        await _enter_customization(page)
    except Exception as e:
        log.warning(f"upload_avatar: enter settings failed: {e}")
        return False

    # 프로필 사진 섹션의 업로드 버튼 (배너/워터마크와 구분 — ytcp-profile-image-upload 로 스코프).
    # YT Studio 는 버튼 클릭 시 native file chooser 다이얼로그를 열므로 Playwright
    # expect_file_chooser 로 intercept (DOM input 직접 set_input_files 는 YT 의
    # lit-element 구조상 일관 동작 안 함).
    # 현재 YT UI: 프로필 이미지 placeholder 가 항상 있어 버튼 라벨이 "변경"(replace-button).
    # 구 UI 의 upload-button / 업로드 텍스트도 fallback 으로 유지.
    try:
        upload_btn = page.locator(
            "ytcp-profile-image-upload ytcp-button#replace-button button, "
            "ytcp-profile-image-upload ytcp-button#upload-button button, "
            "ytcp-profile-image-upload button:has-text('변경'), "
            "ytcp-profile-image-upload button:has-text('업로드'), "
            "ytcp-profile-image-upload button:has-text('Change'), "
            "ytcp-profile-image-upload button:has-text('Upload')"
        ).first
        async with page.expect_file_chooser(timeout=10_000) as fc_info:
            try:
                await human_click(upload_btn, timeout=8_000)
            except Exception:
                await upload_btn.click(timeout=8_000)
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

    # 게시 — Playwright locator.click 으로 trusted 이벤트 보장 (human_click 도 내부
    # 동일하지만 detached/bounding_box 실패 fallback 때문에 명시적 locator.click 백업 병행).
    try:
        publish = page.locator("ytcp-button#publish-button button").first
        await publish.wait_for(timeout=8_000)
        try:
            await human_click(publish, timeout=5_000)
        except Exception:
            await publish.click(timeout=5_000)
        await random_delay(3.0, 5.0)
    except Exception as e:
        log.warning(f"avatar publish failed: {e}")
        return False

    # 게시 확인 모달 — 필요 시 '확인' 클릭
    try:
        confirmed = await page.evaluate("""() => {
          const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
            .filter(d => d.offsetParent !== null && (d.innerText||'').trim());
          for (const d of dlgs) {
            const btn = Array.from(d.querySelectorAll('button'))
              .find(b => b.offsetParent !== null && ['확인','OK','계속','게시','저장'].includes((b.innerText||'').trim()));
            if (btn) { btn.click(); return 'clicked'; }
          }
          return 'none';
        }""")
        if confirmed == "clicked":
            await random_delay(2.0, 3.0)
    except Exception:
        pass

    # 저장 검증 — 서버 커밋 여부는 /editing/profile 의 로컬 preview 가 아닌
    # 채널 헤더의 avatar 이미지 src 로 확인. yt3.ggpht.com 도메인에 해시 변경이
    # 일어나면 서버 저장 성공. data:image/... base64 는 로컬 preview 만.
    # Studio 대시보드로 이동해 avatar-btn 을 확인 — /editing/profile 를 그대로 reload
    # 하면 페이지 컨텍스트가 파괴되어 evaluate 가 던지는 경우가 있음.
    await random_delay(3.0, 5.0)
    real_src = None
    for attempt in range(3):
        try:
            await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded")
            await random_delay(3.0, 5.0)
            real_src = await page.evaluate("""() => {
              const candidates = [
                document.querySelector('#avatar-btn img'),
                document.querySelector('ytcp-entity-avatar img'),
                document.querySelector('#account-menu-button img'),
              ].filter(x => x && x.src && !x.src.startsWith('data:'));
              return candidates.length ? candidates[0].src : null;
            }""")
            if real_src and isinstance(real_src, str) and real_src.startswith("http"):
                break
            await random_delay(2.0, 3.0)
        except Exception as e:
            log.debug(f"upload_avatar verify attempt {attempt+1} failed: {e}")
            await random_delay(2.0, 3.0)

    if not real_src or not isinstance(real_src, str) or not real_src.startswith("http"):
        log.warning(f"upload_avatar: could not verify server-side avatar (src={real_src!r})")
        return False
    log.info(f"avatar uploaded from {avatar_path} (verified server src)")
    return True
