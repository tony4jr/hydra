"""Task executor — bridges scheduler to browser actions.

Takes a pending CampaignStep or LikeBoostQueue item and
executes it through a real browser session.
"""

import asyncio
import json
import random
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core.enums import StepStatus, ActionType
from hydra.core.campaign import generate_step_content
from hydra.core.scheduler import mark_done, mark_failed
from hydra.browser.driver import open_browser
from hydra.browser import actions
from hydra.db.models import (
    CampaignStep, Campaign, Video, Account, LikeBoostQueue, ActionLog,
)
from hydra.ghost.detector import report_ghost_check
from hydra.like_boost.engine import complete_boost, schedule_like_boost
from hydra.infra import telegram
from hydra.infra.ip import rotate_ip, log_ip_usage, end_ip_usage, check_ip_available

log = get_logger("executor")


async def execute_step(db: Session, step: CampaignStep, device_id: str | None = None):
    """Execute a single campaign step via browser.

    Full flow:
    1. Rotate IP (if device available)
    2. Open browser (AdsPower)
    3. Navigate to video
    4. Generate comment content (if not yet)
    5. Post comment/reply
    6. Log action
    7. Schedule like boost (if seed step)
    """
    campaign = db.query(Campaign).get(step.campaign_id)
    video = db.query(Video).get(campaign.video_id)
    account = db.query(Account).get(step.account_id)

    if not account.adspower_profile_id:
        mark_failed(db, step, "No AdsPower profile")
        return

    ip_log_id = None

    try:
        # 1. IP rotation
        current_ip = None
        if device_id:
            current_ip = await rotate_ip(device_id)
            if not check_ip_available(db, current_ip):
                # IP was recently used by another account — rotate again
                current_ip = await rotate_ip(device_id)

            ip_record = log_ip_usage(db, account.id, current_ip, device_id)
            ip_log_id = ip_record.id

        # 2. Generate content if needed
        if not step.content:
            generate_step_content(db, step)

        # 3. Open browser and execute
        async with open_browser(account.adspower_profile_id) as session:
            page = session.page

            # Navigate to video
            await session.goto(video.url, timeout=30000)
            await actions.random_delay(2, 4)

            # Handle captcha if present
            from hydra.infra.captcha import solve_youtube_captcha
            await solve_youtube_captcha(page)

            # Handle ads
            await actions.handle_ad(page)

            # Watch briefly before commenting (look natural)
            watch_sec = random.randint(10, 60)
            await actions.watch_video(page, watch_sec)

            # Scroll to comments
            await actions.scroll_to_comments(page)
            await actions.random_delay(1, 3)

            # Post comment or reply
            # post_comment/post_reply return comment_id (str) on success, None on failure
            result = None
            if step.type == "comment":
                result = await actions.post_comment(page, step.content)
            elif step.type == "reply":
                # Find parent comment to reply to
                if step.parent_step_id is not None:
                    parent = (
                        db.query(CampaignStep)
                        .filter(
                            CampaignStep.campaign_id == campaign.id,
                            CampaignStep.step_number == step.parent_step_id + 1,
                        )
                        .first()
                    )
                    if parent and parent.youtube_comment_id:
                        selector = f"[data-comment-id='{parent.youtube_comment_id}']"
                        result = await actions.post_reply(page, selector, step.content)
                    else:
                        # Fallback: reply to first comment thread
                        selector = "ytd-comment-thread-renderer:first-child"
                        result = await actions.post_reply(page, selector, step.content)
                else:
                    result = await actions.post_comment(page, step.content)

            if result is not None:
                # Save youtube_comment_id to step
                if result:
                    step.youtube_comment_id = result

                # Log action with youtube_comment_id
                action_log = ActionLog(
                    account_id=account.id,
                    video_id=video.id,
                    campaign_id=campaign.id,
                    action_type=ActionType.COMMENT if step.type == "comment" else ActionType.REPLY,
                    is_promo=True,
                    content=step.content,
                    youtube_comment_id=result or None,
                    ip_address=current_ip,
                    duration_sec=watch_sec,
                )
                db.add(action_log)

                mark_done(db, step)
                log.info(f"Step #{step.id} executed successfully")

                # Schedule like boost for seed step
                if step.step_number == 1:
                    from hydra.core.scenarios import get_template, Scenario
                    template = get_template(Scenario(campaign.scenario))
                    schedule_like_boost(db, campaign, step)

            else:
                mark_failed(db, step, "Comment/reply post failed")

    except Exception as e:
        log.error(f"Step #{step.id} execution error: {e}")
        mark_failed(db, step, str(e))

    finally:
        if ip_log_id:
            end_ip_usage(db, ip_log_id)


async def execute_like_boost(db: Session, boost: LikeBoostQueue, device_id: str | None = None):
    """Execute a single like boost action.

    Flow:
    1. Rotate IP
    2. Open browser
    3. Navigate to video
    4. Watch briefly (10~30s)
    5. Scroll to comments
    6. Like surrounding comments (camouflage)
    7. Like our target comment
    8. More surrounding likes
    9. Ghost check (is our comment visible?)
    10. Maybe like the video too
    """
    campaign = db.query(Campaign).get(boost.campaign_id)
    video = db.query(Video).get(campaign.video_id)
    account = db.query(Account).get(boost.account_id)

    # Get target step to find our comment
    target_step = db.query(CampaignStep).get(boost.target_step_id)

    if not account or not account.adspower_profile_id:
        boost.status = "failed"
        db.commit()
        return

    ip_log_id = None

    try:
        # IP rotation
        current_ip = None
        if device_id:
            current_ip = await rotate_ip(device_id)
            ip_record = log_ip_usage(db, account.id, current_ip, device_id)
            ip_log_id = ip_record.id

        async with open_browser(account.adspower_profile_id) as session:
            page = session.page

            # Navigate
            await session.goto(video.url, timeout=30000)
            await actions.random_delay(2, 4)
            await actions.handle_ad(page)

            # Short watch
            await actions.watch_video(page, random.randint(10, 30))

            # Scroll to comments
            found = await actions.scroll_to_comments(page)
            if not found:
                boost.status = "failed"
                db.commit()
                return

            # Ghost check: is our comment visible?
            ghost_result = "visible"
            if target_step and target_step.youtube_comment_id:
                ghost_result = await actions.check_ghost(page, target_step.youtube_comment_id)
                report_ghost_check(db, campaign, ghost_result, account.id)

            if ghost_result == "suspicious":
                # Don't like a ghost comment
                log.warning(f"Ghost suspected, skipping like boost #{boost.id}")
                boost.status = "failed"
                db.commit()
                return

            # Like surrounding comments first (camouflage)
            surrounding_done = 0
            comments = page.locator("ytd-comment-thread-renderer")
            total_comments = await comments.count()

            # Like 2~5 surrounding comments with 0~2 existing likes
            for _ in range(min(boost.surrounding_likes_count, total_comments)):
                idx = random.randint(0, min(total_comments - 1, 20))
                try:
                    comment_el = comments.nth(idx)
                    like_btn = comment_el.locator("#like-button button, like-button-view-model button").first
                    # Check if already liked
                    pressed = await like_btn.get_attribute("aria-pressed")
                    if pressed != "true":
                        await like_btn.click()
                        surrounding_done += 1
                        await actions.random_delay(1, 3)
                except Exception:
                    continue

            # Like OUR comment
            if target_step and target_step.youtube_comment_id:
                try:
                    our_comment = page.locator(f"[data-comment-id='{target_step.youtube_comment_id}']")
                    if await our_comment.count() > 0:
                        like_btn = our_comment.locator("#like-button button, like-button-view-model button").first
                        await like_btn.click()
                        await actions.random_delay(1, 2)
                except Exception as e:
                    log.warning(f"Failed to like target comment: {e}")

            # More surrounding likes after
            extra = random.randint(1, 3)
            for _ in range(min(extra, total_comments)):
                idx = random.randint(0, min(total_comments - 1, 20))
                try:
                    comment_el = comments.nth(idx)
                    like_btn = comment_el.locator("#like-button button, like-button-view-model button").first
                    pressed = await like_btn.get_attribute("aria-pressed")
                    if pressed != "true":
                        await like_btn.click()
                        surrounding_done += 1
                        await actions.random_delay(1, 3)
                except Exception:
                    continue

            # Maybe like the video too (30%)
            if random.random() < 0.30:
                await actions.click_like_button(page, "video")

            # Log
            action_log = ActionLog(
                account_id=account.id,
                video_id=video.id,
                campaign_id=campaign.id,
                action_type=ActionType.LIKE_COMMENT,
                is_promo=True,
                ip_address=current_ip,
            )
            db.add(action_log)

            complete_boost(db, boost, surrounding_done)
            log.info(f"Like boost #{boost.id} done (surrounding: {surrounding_done})")

    except Exception as e:
        log.error(f"Like boost #{boost.id} error: {e}")
        boost.status = "failed"
        db.commit()

    finally:
        if ip_log_id:
            end_ip_usage(db, ip_log_id)
