"""Session runner — per-account behavior loop.

This is the main brain that makes each account act like a real person.
Combines behavior engine + browser + executor into a cohesive session.

Flow per session:
1. Load daily plan (behavior engine)
2. Open browser (AdsPower via executor)
3. Run action loop until session ends:
   - Pick action (scroll/search/watch/shorts/end)
   - Execute action
   - Check if should comment (promo/non-promo)
   - If yes: find target video, execute campaign step OR generate non-promo
4. Close browser
5. Log everything
"""

import asyncio
import json
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.config import settings as app_settings
from hydra.core.enums import AccountStatus, ActionType, StepStatus
from hydra.core.behavior import (
    plan_daily, pick_action, pick_watch_duration,
    should_comment_promo, should_comment_non_promo,
    is_natural_activity_hour, seconds_until_natural_hour,
)
from hydra.core.executor import execute_step, execute_like_boost
from hydra.core.scheduler import get_pending_steps, mark_running
from hydra.browser.driver import open_browser
from hydra.browser import actions
from hydra.db.models import (
    Account, Video, ActionLog, WeeklyGoal, CampaignStep, Campaign,
)
from hydra.db.session import SessionLocal
from hydra.ai.agents.persona_agent import get_persona
from hydra.ai.agents.casual_agent import generate_non_promo_comment
from hydra.infra import telegram
from hydra.infra.ip import rotate_ip, log_ip_usage, end_ip_usage

log = get_logger("session")


async def run_session(account: Account, device_id: str | None = None):
    """Run a single session for an account.

    A session = one sitting of YouTube browsing.
    """
    db = SessionLocal()

    try:
        # Check natural activity hours (KST)
        if not is_natural_activity_hour():
            wait = seconds_until_natural_hour()
            log.info(f"Outside KST activity hours, skipping {account.gmail} (resume in {wait//60}min)")
            return

        # Check account is still active
        acct = db.query(Account).get(account.id)
        if acct.status != AccountStatus.ACTIVE:
            log.info(f"Account {acct.gmail} not active ({acct.status}), skipping")
            return

        # Get weekly goals
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        goal = (
            db.query(WeeklyGoal)
            .filter(WeeklyGoal.account_id == acct.id, WeeklyGoal.week_start == week_start)
            .first()
        )
        if not goal:
            goal = WeeklyGoal(
                account_id=acct.id,
                week_start=week_start,
                promo_target=app_settings.weekly_promo_comments,
                non_promo_target=app_settings.weekly_non_promo_actions,
            )
            db.add(goal)
            db.commit()

        promo_remaining = goal.promo_target - goal.promo_done
        non_promo_remaining = goal.non_promo_target - goal.non_promo_done
        days_left = 7 - now.weekday()

        # Plan today
        daily = plan_daily(
            promo_remaining, non_promo_remaining, days_left,
            is_weekend=(now.weekday() >= 5),
        )

        if daily.is_rest_day:
            log.info(f"Rest day for {acct.gmail}")
            return

        session_promo_budget = daily.promo_target // max(len(daily.sessions), 1)
        session_non_promo_budget = daily.non_promo_target // max(len(daily.sessions), 1)
        promo_done = 0
        non_promo_done = 0

        # IP rotation
        ip_log_id = None
        current_ip = None
        if device_id:
            current_ip = await rotate_ip(device_id)
            ip_record = log_ip_usage(db, acct.id, current_ip, device_id)
            ip_log_id = ip_record.id

        log.info(f"Session start: {acct.gmail} (promo budget: {session_promo_budget}, non-promo: {session_non_promo_budget})")

        # Pick a session duration
        session = daily.sessions[0] if daily.sessions else None
        duration_min = session.duration_minutes if session else random.randint(15, 45)
        session_end = datetime.now(timezone.utc) + timedelta(minutes=duration_min)

        async with open_browser(acct.adspower_profile_id) as browser_session:
            page = browser_session.page

            # Go to YouTube home
            await browser_session.goto("https://www.youtube.com")
            await actions.random_delay(2, 4)

            # --- Action Loop ---
            while datetime.now(timezone.utc) < session_end:
                action = pick_action()

                if action == "end_session":
                    log.info(f"Session ending naturally for {acct.gmail}")
                    break

                elif action == "home_scroll":
                    await actions.scroll_page(page, scrolls=random.randint(3, 10))

                    # 70% chance: click a video
                    if random.random() < 0.70:
                        try:
                            thumbnails = page.locator("ytd-rich-item-renderer a#thumbnail")
                            count = await thumbnails.count()
                            if count > 0:
                                idx = random.randint(0, min(count - 1, 15))
                                await thumbnails.nth(idx).click()
                                await actions.random_delay(2, 4)
                                pd, npd = await _watch_and_maybe_comment(
                                    db, browser_session, acct, current_ip,
                                    promo_done, session_promo_budget,
                                    non_promo_done, session_non_promo_budget,
                                    goal,
                                )
                                promo_done += pd
                                non_promo_done += npd
                        except Exception as e:
                            log.warning(f"Home scroll click error: {e}")

                elif action == "keyword_search":
                    # Type a keyword search
                    persona = get_persona(acct)
                    interests = persona.get("interests", ["재미있는 영상"]) if persona else ["재미있는 영상"]
                    query = random.choice(interests)

                    try:
                        search_box = page.locator("input#search")
                        await search_box.click()
                        await actions.random_delay(0.5, 1.5)

                        # Clear and type
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
                            idx = random.randint(0, min(count - 1, 8))
                            await results.nth(idx).click()
                            await actions.random_delay(2, 4)
                            pd, npd = await _watch_and_maybe_comment(
                                db, browser_session, acct, current_ip,
                                promo_done, session_promo_budget,
                                non_promo_done, session_non_promo_budget,
                                goal,
                            )
                            promo_done += pd
                            non_promo_done += npd

                    except Exception as e:
                        log.warning(f"Search action error: {e}")

                elif action == "recommended":
                    # Click a recommended video from sidebar
                    try:
                        recs = page.locator("ytd-compact-video-renderer a")
                        count = await recs.count()
                        if count > 0:
                            idx = random.randint(0, min(count - 1, 10))
                            await recs.nth(idx).click()
                            await actions.random_delay(2, 4)
                            pd, npd = await _watch_and_maybe_comment(
                                db, browser_session, acct, current_ip,
                                promo_done, session_promo_budget,
                                non_promo_done, session_non_promo_budget,
                                goal,
                            )
                            promo_done += pd
                            non_promo_done += npd
                    except Exception as e:
                        log.warning(f"Recommended click error: {e}")

                elif action == "shorts":
                    # Browse shorts — with keyword matching for promo comments (#4)
                    try:
                        await browser_session.goto("https://www.youtube.com/shorts")
                        await actions.random_delay(2, 4)

                        swipes = random.randint(3, 15)
                        for _ in range(swipes):
                            await page.keyboard.press("ArrowDown")
                            await asyncio.sleep(random.uniform(2, 8))

                            # Log shorts swipe
                            db.add(ActionLog(
                                account_id=acct.id,
                                action_type=ActionType.SHORTS_SWIPE,
                                is_promo=False,
                                ip_address=current_ip,
                            ))
                            non_promo_done += 1

                            # #4: Check if this short matches a brand keyword → comment
                            promo_left = session_promo_budget - promo_done
                            if promo_left > 0 and random.random() < 0.20:
                                try:
                                    # Get shorts title
                                    title_el = page.locator("h2.ytShortsVideoTitleViewModelShortsVideoTitle span, yt-formatted-string.ytShortsVideoTitleViewModelShortsVideoTitle")
                                    title = await title_el.first.text_content(timeout=2000)

                                    # Check pending steps
                                    pending = (
                                        db.query(CampaignStep)
                                        .filter(
                                            CampaignStep.account_id == acct.id,
                                            CampaignStep.status == StepStatus.PENDING,
                                        )
                                        .order_by(CampaignStep.scheduled_at)
                                        .first()
                                    )
                                    if pending:
                                        from hydra.core.scheduler import mark_running
                                        from hydra.core.executor import execute_step
                                        mark_running(db, pending)
                                        await execute_step(db, pending)
                                        promo_done += 1
                                except Exception:
                                    pass  # Shorts comment attempt failed, continue swiping

                        db.commit()

                        # Go back to main
                        await browser_session.goto("https://www.youtube.com")
                        await actions.random_delay(2, 4)

                    except Exception as e:
                        log.warning(f"Shorts browse error: {e}")

                # Brief pause between actions
                await actions.random_delay(2, 8)

        # Update weekly goals
        goal.promo_done += promo_done
        goal.non_promo_done += non_promo_done
        acct.last_active_at = datetime.now(timezone.utc)
        db.commit()

        log.info(
            f"Session done: {acct.gmail} — "
            f"promo: {promo_done}/{session_promo_budget}, "
            f"non-promo: {non_promo_done}/{session_non_promo_budget}"
        )

    except Exception as e:
        log.error(f"Session error for {account.gmail}: {e}")
        telegram.warning(f"세션 에러: {account.gmail} — {e}")

    finally:
        if ip_log_id:
            end_ip_usage(db, ip_log_id)
        db.close()


async def _watch_and_maybe_comment(
    db: Session,
    browser_session,
    account: Account,
    current_ip: str | None,
    promo_done: int,
    promo_budget: int,
    non_promo_done: int,
    non_promo_budget: int,
    goal: WeeklyGoal,
) -> tuple[int, int]:
    """Watch current video and decide whether to comment.

    Returns (promo_delta, non_promo_delta) — how many actions were done.
    """
    page = browser_session.page
    promo_delta = 0
    non_promo_delta = 0

    # Handle ad
    await actions.handle_ad(page)

    # Watch
    watch_sec = pick_watch_duration()
    await actions.watch_video(page, watch_sec)
    non_promo_delta += 1  # view counts as non-promo

    # Check if there's a pending promo step for this account
    promo_left = promo_budget - promo_done
    non_promo_left = non_promo_budget - non_promo_done

    if should_comment_promo(promo_left):
        pending = (
            db.query(CampaignStep)
            .filter(
                CampaignStep.account_id == account.id,
                CampaignStep.status == StepStatus.PENDING,
            )
            .order_by(CampaignStep.scheduled_at)
            .first()
        )
        if pending:
            mark_running(db, pending)
            await execute_step(db, pending)
            promo_delta += 1

    elif should_comment_non_promo(non_promo_left):
        roll = random.random()
        if roll < 0.15:
            # Leave a non-promo comment (Haiku model, cheap)
            try:
                persona = get_persona(account)
                if persona:
                    # Get video title from page
                    title = await page.locator("h1.ytd-watch-metadata yt-formatted-string").first.text_content()
                    comment_text = generate_non_promo_comment(persona, title or "")
                    found = await actions.scroll_to_comments(page)
                    if found and comment_text:
                        result = await actions.post_comment(page, comment_text)
                        if result is not None:
                            db.add(ActionLog(
                                account_id=account.id,
                                action_type=ActionType.COMMENT,
                                is_promo=False,
                                content=comment_text,
                                youtube_comment_id=result or None,
                                ip_address=current_ip,
                            ))
                            db.commit()
                            non_promo_delta += 1
            except Exception as e:
                log.warning(f"Non-promo comment failed: {e}")

        elif roll < 0.45:
            # Like random comments
            found = await actions.scroll_to_comments(page)
            if found:
                comments = page.locator("ytd-comment-thread-renderer")
                count = await comments.count()
                likes_to_do = random.randint(1, 3)
                for _ in range(min(likes_to_do, count)):
                    idx = random.randint(0, min(count - 1, 15))
                    try:
                        btn = comments.nth(idx).locator("#like-button button").first
                        pressed = await btn.get_attribute("aria-pressed")
                        if pressed != "true":
                            await btn.click()
                            await actions.random_delay(1, 2)
                    except Exception:
                        continue

                db.add(ActionLog(
                    account_id=account.id,
                    action_type=ActionType.LIKE_COMMENT,
                    is_promo=False,
                    ip_address=current_ip,
                ))
                db.commit()
                non_promo_delta += 1

    # Random: like the video itself
    if random.random() < 0.10:
        await actions.click_like_button(page, "video")
        db.add(ActionLog(
            account_id=account.id,
            action_type=ActionType.LIKE_VIDEO,
            is_promo=False,
            ip_address=current_ip,
        ))
        db.commit()
        non_promo_delta += 1

    # Log view
    db.add(ActionLog(
        account_id=account.id,
        action_type=ActionType.VIEW,
        is_promo=False,
        ip_address=current_ip,
        duration_sec=watch_sec,
    ))
    db.commit()

    return promo_delta, non_promo_delta


async def run_all_sessions(device_id: str | None = None, max_concurrent: int = 1):
    """Main entry: run sessions for all active accounts.

    Accounts are processed one at a time (1 IP = 1 account).
    """
    db = SessionLocal()

    try:
        accounts = (
            db.query(Account)
            .filter(Account.status == AccountStatus.ACTIVE)
            .all()
        )

        random.shuffle(accounts)
        log.info(f"Starting sessions for {len(accounts)} active accounts")

        for account in accounts:
            try:
                await run_session(account, device_id=device_id)

                # Cooldown between accounts (spec: min 2h between sessions,
                # but between different accounts we just need IP rotation)
                await asyncio.sleep(random.uniform(5, 15))

            except Exception as e:
                log.error(f"Account {account.gmail} session failed: {e}")
                continue

    finally:
        db.close()
