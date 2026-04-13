"""Warmup session runner — makes warmup accounts act like real users.

Spec 2.1.4:
Warmup period allows:
  - Video watching (keyword related + unrelated mix)
  - Home feed scrolling
  - Search
  - Likes (video + other people's comments)
  - Subscribe (1~2 related channels/day)
  - NO comments, NO replies, NO promo

This runs like session_runner but with restrictions.
"""

import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import AccountStatus, ActionType
from hydra.core.behavior import pick_watch_duration
from hydra.browser.driver import open_browser
from hydra.browser import actions
from hydra.db.models import Account, ActionLog
from hydra.db.session import SessionLocal
from hydra.accounts.manager import transition
from hydra.ai.agents.persona_agent import get_persona
from hydra.infra import telegram
from hydra.infra.ip import rotate_ip, log_ip_usage, end_ip_usage

log = get_logger("warmup")


async def run_warmup_session(account: Account, device_id: str | None = None):
    """Run a warmup session — watch, scroll, like. No comments."""
    db = SessionLocal()

    try:
        acct = db.query(Account).get(account.id)
        if acct.status != AccountStatus.WARMUP:
            return

        ip_log_id = None
        current_ip = None

        if device_id:
            current_ip = await rotate_ip(device_id)
            ip_record = log_ip_usage(db, acct.id, current_ip, device_id)
            ip_log_id = ip_record.id

        # Session duration: 15~45 min
        duration_min = random.randint(15, 45)

        log.info(f"Warmup session start: {acct.gmail} ({duration_min}min)")

        async with open_browser(acct.adspower_profile_id) as session:
            page = session.page

            # Load cookies if available
            from hydra.accounts.setup import load_cookies
            if not await load_cookies(session, acct):
                from hydra.accounts.setup import login_gmail
                success = await login_gmail(session, acct)
                if not success:
                    transition(db, acct, AccountStatus.LOGIN_FAILED, "warmup login failed")
                    return

            await session.goto("https://www.youtube.com")
            await actions.random_delay(2, 4)

            import time
            end_time = time.time() + duration_min * 60

            views_done = 0
            likes_done = 0

            while time.time() < end_time:
                # Pick warmup action
                roll = random.random()

                if roll < 0.30:
                    # Home feed scroll + click video
                    await actions.scroll_page(page, scrolls=random.randint(2, 6))

                    if random.random() < 0.60:
                        try:
                            thumbs = page.locator("ytd-rich-item-renderer a#thumbnail")
                            count = await thumbs.count()
                            if count > 0:
                                await thumbs.nth(random.randint(0, min(count-1, 12))).click()
                                await actions.random_delay(2, 4)
                                await actions.handle_ad(page)

                                watch_sec = pick_watch_duration()
                                await actions.watch_video(page, watch_sec)
                                views_done += 1

                                # Maybe like the video (30%)
                                if random.random() < 0.30:
                                    await actions.click_like_button(page, "video")
                                    likes_done += 1

                                db.add(ActionLog(
                                    account_id=acct.id,
                                    action_type=ActionType.VIEW,
                                    is_promo=False,
                                    ip_address=current_ip,
                                    duration_sec=watch_sec,
                                ))
                                db.commit()

                                # Go back to home
                                await page.go_back()
                                await actions.random_delay(1, 3)
                        except Exception as e:
                            log.warning(f"Warmup video click error: {e}")

                elif roll < 0.55:
                    # Keyword search based on persona interests
                    persona = get_persona(acct)
                    interests = persona.get("interests", ["재미있는 영상"]) if persona else ["재미있는 영상"]
                    query = random.choice(interests)

                    try:
                        search_box = page.locator("input#search")
                        await search_box.click()
                        await actions.random_delay(0.5, 1)
                        await search_box.fill("")
                        for char in query:
                            await page.keyboard.type(char)
                            await asyncio.sleep(random.uniform(0.05, 0.15))
                        await page.keyboard.press("Enter")
                        await actions.random_delay(2, 4)

                        # Click a result
                        results = page.locator("ytd-video-renderer a#thumbnail")
                        count = await results.count()
                        if count > 0:
                            await results.nth(random.randint(0, min(count-1, 5))).click()
                            await actions.random_delay(2, 3)
                            await actions.handle_ad(page)
                            watch_sec = pick_watch_duration()
                            await actions.watch_video(page, watch_sec)
                            views_done += 1

                            db.add(ActionLog(
                                account_id=acct.id,
                                action_type=ActionType.SEARCH,
                                is_promo=False,
                                ip_address=current_ip,
                                content=query,
                            ))
                            db.commit()
                    except Exception as e:
                        log.warning(f"Warmup search error: {e}")

                elif roll < 0.70:
                    # Browse shorts
                    try:
                        await session.goto("https://www.youtube.com/shorts")
                        await actions.random_delay(2, 3)
                        for _ in range(random.randint(3, 10)):
                            await page.keyboard.press("ArrowDown")
                            await asyncio.sleep(random.uniform(2, 6))
                        views_done += 1
                        await session.goto("https://www.youtube.com")
                        await actions.random_delay(2, 3)
                    except Exception as e:
                        log.warning(f"Warmup shorts error: {e}")

                elif roll < 0.85:
                    # Like other people's comments
                    try:
                        found = await actions.scroll_to_comments(page)
                        if found:
                            comments = page.locator("ytd-comment-thread-renderer")
                            count = await comments.count()
                            to_like = random.randint(1, 3)
                            for _ in range(min(to_like, count)):
                                idx = random.randint(0, min(count-1, 10))
                                btn = comments.nth(idx).locator("#like-button button").first
                                pressed = await btn.get_attribute("aria-pressed")
                                if pressed != "true":
                                    await btn.click()
                                    likes_done += 1
                                    await actions.random_delay(1, 3)

                            db.add(ActionLog(
                                account_id=acct.id,
                                action_type=ActionType.LIKE_COMMENT,
                                is_promo=False,
                                ip_address=current_ip,
                            ))
                            db.commit()
                    except Exception:
                        pass

                else:
                    # Subscribe to a related channel (max 1~2/day)
                    try:
                        sub_btn = page.locator(
                            "ytd-subscribe-button-renderer button:not([subscribed])"
                        ).first
                        if await sub_btn.is_visible(timeout=2000):
                            await sub_btn.click()
                            await actions.random_delay(2, 4)

                            db.add(ActionLog(
                                account_id=acct.id,
                                action_type=ActionType.SUBSCRIBE,
                                is_promo=False,
                                ip_address=current_ip,
                            ))
                            db.commit()
                    except Exception:
                        pass

                await actions.random_delay(3, 10)

        # Update account
        acct.last_active_at = datetime.now(timezone.utc)
        db.commit()

        log.info(f"Warmup done: {acct.gmail} — views={views_done}, likes={likes_done}")

    except Exception as e:
        log.error(f"Warmup session error for {account.gmail}: {e}")
        telegram.warning(f"웜업 세션 에러: {account.gmail} — {e}")

    finally:
        if ip_log_id:
            end_ip_usage(db, ip_log_id)
        db.close()


async def run_all_warmups(device_id: str | None = None):
    """Run warmup sessions for all warmup-status accounts."""
    db = SessionLocal()
    try:
        accounts = (
            db.query(Account)
            .filter(Account.status == AccountStatus.WARMUP)
            .all()
        )

        random.shuffle(accounts)
        log.info(f"Running warmup for {len(accounts)} accounts")

        for account in accounts:
            await run_warmup_session(account, device_id=device_id)
            await asyncio.sleep(random.uniform(5, 15))

    finally:
        db.close()
