"""각 온보딩 목표의 detect + apply 인터페이스.

Goal 은 동일 인터페이스로 호출되어 verifier 가 순차 실행한다.
실행 가능한 goals 는 이 파일 하단의 ALL_GOALS 리스트에 등록.
"""
from typing import Literal, Protocol, runtime_checkable


State = Literal["done", "not_done", "blocked"]
ApplyResult = Literal["done", "failed", "blocked"]


@runtime_checkable
class Goal(Protocol):
    name: str
    required: bool

    async def detect(self, page, acct) -> State: ...
    async def apply(self, page, acct) -> ApplyResult: ...


# --- 실제 goal 구현 ---
from worker.login import check_logged_in
from worker.language_setup import ensure_korean_language
from worker.google_account import update_account_name
from worker.google_account import register_otp_authenticator, handle_identity_challenge
from worker.data_saver import set_primary_video_language
from worker.channel_actions import (
    rename_channel, change_handle, pick_avatar_file, upload_avatar, _enter_customization,
    set_full_channel_profile, StudioIdentityChallengeRequired,
)
from hydra.core import crypto
from hydra.core.enums import WARMUP_DAYS
from hydra.db.session import SessionLocal
from hydra.db.models import Account
from onboarding.login_fsm import run_login_fsm
from hydra.core.logger import get_logger
from datetime import datetime, timedelta, UTC

log = get_logger("onboarding.goals")


class LoginGoal:
    name = "login"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            pass
        return "done" if await check_logged_in(page) else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        status, final_url = await run_login_fsm(page, acct)
        log.info(f"login_fsm → {status} @ {final_url[:80]}")

        # ipp 우회 성공 시 DB 컬럼 + notes 태그 + acct.ipp_flagged 전파.
        if getattr(acct, "_ipp_flagged", False):
            db = SessionLocal()
            try:
                row = db.get(Account, acct.id)
                row.ipp_flagged = True
                tag = f"login_ipp_bypassed @ {datetime.now(UTC).isoformat(timespec='seconds')}"
                row.notes = (row.notes + "\n" + tag) if row.notes else tag
                db.commit()
            finally:
                db.close()
            acct.ipp_flagged = True
            log.info(f"account #{acct.id} ipp_flagged=True (google-account goals will skip)")

        if status == "done":
            return "done"
        if status == "dead":
            # /challenge/dp — 계정 사망. retired 처리 (1:1 프로필이라 같이 폐기).
            db = SessionLocal()
            try:
                row = db.get(Account, acct.id)
                row.status = "retired"
                row.retired_at = datetime.now(UTC)
                row.retired_reason = f"login /challenge/dp (dead) @ {final_url[:200]}"
                db.commit()
            finally:
                db.close()
            log.warning(f"account #{acct.id} retired — /challenge/dp")
            return "blocked"
        return "failed"


class UiLangKoGoal:
    name = "ui_lang_ko"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://myaccount.google.com/language",
                            wait_until="domcontentloaded", timeout=20_000)
            ok = await page.evaluate("""() => {
              const t = document.body.innerText || '';
              return /선호 언어[\\s\\S]{0,40}한국어/.test(t);
            }""")
            return "done" if ok else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        try:
            return "done" if await ensure_korean_language(page) else "failed"
        except Exception as e:
            log.warning(f"ui_lang_ko apply err: {e}")
            return "failed"


class DisplayNameGoal:
    name = "display_name"
    required = True

    async def detect(self, page, acct) -> State:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("name") or "").strip()
        if not target:
            return "blocked"
        try:
            await page.goto("https://myaccount.google.com/profile/name",
                            wait_until="domcontentloaded", timeout=20_000)
            txt = await page.evaluate("() => document.body.innerText || ''")
            compact = target.replace(" ", "")
            return "done" if compact in txt.replace(" ", "") else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        target = (persona.get("name") or "").strip()
        if not target:
            return "blocked"
        pwd = crypto.decrypt(acct.password) if acct.password else None
        try:
            return "done" if await update_account_name(page, target, password=pwd) else "failed"
        except Exception as e:
            log.warning(f"display_name apply err: {e}")
            return "failed"


class TotpSecretGoal:
    """B그룹 — DB 에 totp_secret 있으면 done. 외부 관찰 불가."""
    name = "totp_secret"
    required = False

    async def detect(self, page, acct) -> State:
        return "done" if acct.totp_secret else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        pwd = crypto.decrypt(acct.password) if acct.password else None
        if not pwd:
            return "failed"
        try:
            secret, _activated = await register_otp_authenticator(page, pwd)
        except Exception as e:
            log.warning(f"totp apply err: {e}")
            return "failed"
        if not secret:
            return "failed"
        db = SessionLocal()
        try:
            row = db.get(Account, acct.id)
            if not row.totp_secret:
                row.totp_secret = crypto.encrypt(secret)
                db.commit()
        finally:
            db.close()
        return "done"


class VideoLangKoGoal:
    name = "video_lang_ko"
    required = False

    async def detect(self, page, acct) -> State:
        # /account_playback 본문에는 선택된 언어가 표시되지 않음 (다이얼로그 내부).
        # apply 의 set_primary_video_language 가 자체 idempotent — 이미 선택됐으면
        # 내부에서 skip 하고 True 리턴. 따라서 detect 는 항상 not_done.
        return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        try:
            return "done" if await set_primary_video_language(page, "한국어") else "failed"
        except Exception as e:
            log.warning(f"video_lang apply err: {e}")
            return "failed"


class IdentityChallengeGoal:
    """Studio 진입 → 본인 인증 모달 감지. locked 면 blocked + 쿨다운."""
    name = "identity_challenge"
    required = True

    async def detect(self, page, acct) -> State:
        try:
            await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=20_000)
            import asyncio as _a
            await _a.sleep(3)
            has = await page.evaluate("""() => {
              const dlgs = Array.from(document.querySelectorAll('tp-yt-paper-dialog, ytcp-dialog, [role="dialog"]'))
                .filter(d => d.offsetParent !== null);
              return dlgs.some(d => (d.innerText||'').includes('본인 인증'));
            }""")
            return "not_done" if has else "done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        pwd = crypto.decrypt(acct.password) if acct.password else None
        try:
            result = await handle_identity_challenge(page, pwd)
        except Exception as e:
            log.warning(f"identity apply err: {e}")
            return "failed"
        if result == "locked":
            from datetime import datetime, timedelta, UTC
            db = SessionLocal()
            try:
                row = db.get(Account, acct.id)
                row.status = "identity_challenge"
                row.identity_challenge_until = datetime.now(UTC) + timedelta(days=7)
                row.identity_challenge_count = (row.identity_challenge_count or 0) + 1
                db.commit()
            finally:
                db.close()
            return "blocked"
        return "done"


async def _read_studio_inputs(page) -> dict:
    """Studio 맞춤설정 페이지에서 name/handle 현재값 읽기."""
    await page.goto("https://studio.youtube.com/", wait_until="domcontentloaded", timeout=20_000)
    import asyncio as _a
    await _a.sleep(3)
    await _enter_customization(page)
    name = await page.evaluate("() => document.querySelector(\"input[placeholder='채널 이름 입력']\")?.value || ''")
    handle = await page.evaluate("() => document.querySelector(\"input[placeholder='핸들 설정']\")?.value || ''")
    return {"name": (name or "").strip(), "handle": (handle or "").strip()}


class ChannelProfileGoal:
    """이름 + 핸들 + 아바타 단일 진입 · 단일 publish (set_full_channel_profile).

    avatar 는 channel_plan.avatar_policy == 'set_during_warmup' 일 때만 업로드.
    name/handle 은 required — 하나라도 실패하면 goal failed. avatar 부분 실패는
    반환 dict 에 avatar_ok=False 로 남지만 goal 은 name+handle 기준으로만 판정.
    """
    name = "channel_profile"
    required = True

    def _targets(self, acct) -> tuple[str, str, str | None]:
        import json as _json
        persona = _json.loads(acct.persona) if acct.persona else {}
        cp = persona.get("channel_plan") or {}
        title = (cp.get("title") or "").strip()
        handle = (cp.get("handle") or "").strip()
        avatar_path = None
        if cp.get("avatar_policy") == "set_during_warmup":
            avatar_path = pick_avatar_file(persona, cp)
        return title, handle, avatar_path

    async def detect(self, page, acct) -> State:
        title, handle, avatar_path = self._targets(acct)
        if not title or not handle:
            return "blocked"
        try:
            cur = await _read_studio_inputs(page)
            name_ok = cur["name"] == title
            handle_ok = cur["handle"].lower().startswith(handle.lower())
            avatar_ok = True
            if avatar_path:
                src = await page.evaluate(
                    "() => document.querySelector('#avatar-btn img')?.src || ''"
                )
                avatar_ok = bool(src) and "AIdro_" not in src
            return "done" if (name_ok and handle_ok and avatar_ok) else "not_done"
        except Exception:
            return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        title, handle, avatar_path = self._targets(acct)
        if not title or not handle:
            return "blocked"
        try:
            res = await set_full_channel_profile(
                page, title, handle, avatar_path=avatar_path
            )
        except StudioIdentityChallengeRequired:
            # Studio 본인 인증 팝업 — 7일 쿨다운 + status 전이.
            db = SessionLocal()
            try:
                row = db.get(Account, acct.id)
                row.status = "identity_challenge"
                row.identity_challenge_until = datetime.now(UTC) + timedelta(days=7)
                row.identity_challenge_count = (row.identity_challenge_count or 0) + 1
                tag = f"studio_auth_challenge @ {datetime.now(UTC).isoformat(timespec='seconds')}"
                row.notes = (row.notes + "\n" + tag) if row.notes else tag
                db.commit()
            finally:
                db.close()
            log.warning(f"account #{acct.id} 7d cooldown — studio auth dialog")
            return "blocked"
        except Exception as e:
            log.warning(f"channel_profile apply err: {e}")
            return "failed"
        if res.get("name_ok") and res.get("handle_ok"):
            if avatar_path and not res.get("avatar_ok"):
                log.warning(f"channel_profile: avatar upload failed (name/handle ok) — continuing")
            return "done"
        log.warning(f"channel_profile partial: {res}")
        return "failed"


class NaturalBrowsingGoal:
    """YT 자연 탐색 — 홈 스크롤 + 검색 1회 + 영상/숏츠 시청 랜덤 (~2~5분).

    Anti-detection 핵심: 채널 설정만 바로 하고 나가는 봇 패턴 회피. onboarding 세션
    안에서 실사용자 같은 체류 시간 + 행동 다양성 확보.

    detect 는 항상 not_done — idempotent 한 단계 아님 (매번 다른 활동 수행).
    """
    name = "natural_browsing"
    required = False

    async def detect(self, page, acct) -> State:
        return "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        import json as _json
        import random as _rand
        import time as _time
        from worker.onboard_session import (
            _do_search, _watch_home_video, _browse_shorts, _scroll_home,
        )
        from worker.search_pool import pick as _pick_query
        from hydra.browser.actions import scroll_page, rep_count, random_delay

        persona = _json.loads(acct.persona) if acct.persona else {}
        duration_min, duration_max = 90, 180  # 1.5~3 분
        target = _rand.uniform(duration_min, duration_max)
        started = _time.time()

        try:
            await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=30_000)
        except Exception as e:
            log.warning(f"natural_browsing goto err: {e}")
            return "failed"
        await random_delay(3.0, 6.0)

        try:
            await scroll_page(page, scrolls=rep_count(2, 5))
        except Exception:
            pass
        await random_delay(3.0, 7.0)

        searched = False
        while (_time.time() - started) < target:
            remaining = target - (_time.time() - started)
            if remaining < 20:
                break
            if not searched and _rand.random() < 0.6:
                q = _pick_query(int(persona.get("age", 25)))
                try:
                    await _do_search(page, q)
                    searched = True
                except Exception as e:
                    log.warning(f"search err: {e}")
                await random_delay(3.0, 8.0)
                continue
            action = _rand.choices(
                ["watch_home_video", "browse_shorts", "scroll_home"],
                weights=[45, 30, 25],
            )[0]
            try:
                if action == "watch_home_video":
                    await _watch_home_video(page)
                elif action == "browse_shorts":
                    await _browse_shorts(page)
                else:
                    await _scroll_home(page)
            except Exception as e:
                log.warning(f"{action} err: {e}")
            await random_delay(4.0, 10.0)

        return "done"


class FinalizeWarmupGoal:
    """필수 goals 모두 통과한 계정만 warmup 상태로 전이. DB 전용."""
    name = "finalize_warmup"
    required = False

    async def detect(self, page, acct) -> State:
        return "done" if acct.status == "warmup" else "not_done"

    async def apply(self, page, acct) -> ApplyResult:
        db = SessionLocal()
        try:
            row = db.get(Account, acct.id)
            row.warmup_group = "B"
            if row.status != "warmup":
                row.status = "warmup"
            if not row.onboard_completed_at:
                row.onboard_completed_at = datetime.now(UTC)
            if not row.warmup_start_date:
                row.warmup_start_date = datetime.now(UTC)
            row.warmup_end_date = row.warmup_start_date + timedelta(
                days=WARMUP_DAYS.get("B", 3)
            )
            if (row.warmup_day or 0) == 0:
                row.warmup_day = 0
            db.commit()
        finally:
            db.close()
        return "done"


ALL_GOALS: list[Goal] = [
    LoginGoal(),
    UiLangKoGoal(),
    DisplayNameGoal(),
    TotpSecretGoal(),
    VideoLangKoGoal(),
    NaturalBrowsingGoal(),   # YT 자연 탐색 — 봇 패턴 회피
    IdentityChallengeGoal(),
    ChannelProfileGoal(),
    FinalizeWarmupGoal(),
]
