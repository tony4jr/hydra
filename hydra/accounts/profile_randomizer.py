"""Channel profile randomization using pool system.

MKT_TUBE ChangeInfoChannels pattern:
- 6 pool types: avatar, banner, name, description, contact, hashtag
- Random select from pool → apply via browser → log history
"""

import json
import random
from datetime import datetime, timezone

from playwright.async_api import Page
from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.browser.driver import open_browser
from hydra.browser import actions
from hydra.db.models import Account, ProfilePool, ChannelProfileHistory

log = get_logger("profile_randomizer")


def pick_from_pool(db: Session, pool_type: str) -> str | None:
    """Pick a random item from a pool type, preferring least-used."""
    items = (
        db.query(ProfilePool)
        .filter(
            ProfilePool.pool_type == pool_type,
            ProfilePool.disabled == False,
        )
        .order_by(ProfilePool.used_count)
        .limit(10)
        .all()
    )
    if not items:
        return None

    chosen = random.choice(items[:5])  # Pick from 5 least-used
    chosen.used_count += 1
    chosen.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return chosen.content


async def randomize_channel_profile(db: Session, account: Account):
    """Apply random profile elements to a YouTube channel.

    Uses AdsPower browser to change channel settings.
    """
    if not account.adspower_profile_id:
        log.warning(f"No AdsPower profile for {account.gmail}")
        return

    # Pick from pools
    name = pick_from_pool(db, "name")
    description = pick_from_pool(db, "description")
    avatar_path = pick_from_pool(db, "avatar")
    banner_path = pick_from_pool(db, "banner")

    async with open_browser(account.adspower_profile_id) as session:
        page = session.page

        # Navigate to YouTube Studio customization
        await session.goto("https://studio.youtube.com")
        await actions.random_delay(3, 5)

        # Click Customization → Branding
        try:
            await page.click("text=Customization, text=맞춤설정")
        except Exception:
            try:
                # Try navigating directly
                await session.goto("https://studio.youtube.com/channel/editing/branding")
            except Exception:
                pass
        await actions.random_delay(2, 4)

        # Change name
        if name:
            try:
                await session.goto("https://studio.youtube.com/channel/editing/basic")
                await actions.random_delay(2, 3)
                name_input = page.locator("input[aria-label*='Name'], input[aria-label*='이름']").first
                await name_input.fill("")
                await name_input.fill(name)
                await actions.random_delay(1, 2)
            except Exception as e:
                log.warning(f"Name change failed: {e}")

        # Change description
        if description:
            try:
                desc_input = page.locator("textarea[aria-label*='Description'], textarea[aria-label*='설명']").first
                await desc_input.fill("")
                await desc_input.fill(description)
                await actions.random_delay(1, 2)
            except Exception as e:
                log.warning(f"Description change failed: {e}")

        # Upload avatar
        if avatar_path:
            try:
                await session.goto("https://studio.youtube.com/channel/editing/branding")
                await actions.random_delay(2, 3)
                upload = page.locator("input[type='file']").first
                await upload.set_input_files(avatar_path)
                await actions.random_delay(3, 5)
                # Confirm crop dialog
                done_btn = page.locator("button:has-text('DONE'), button:has-text('완료')").first
                await done_btn.click()
                await actions.random_delay(2, 3)
            except Exception as e:
                log.warning(f"Avatar upload failed: {e}")

        # Save changes
        try:
            publish_btn = page.locator("button:has-text('PUBLISH'), button:has-text('게시')").first
            await publish_btn.click()
            await actions.random_delay(2, 4)
        except Exception as e:
            log.warning(f"Save failed: {e}")

    # Log history
    history = ChannelProfileHistory(
        account_id=account.id,
        avatar_path=avatar_path,
        banner_path=banner_path,
        name=name,
        description=description,
    )
    db.add(history)
    db.commit()

    log.info(f"Profile randomized for {account.gmail}: name={name}")


async def batch_randomize(db: Session, account_ids: list[int] | None = None):
    """Randomize profiles for multiple accounts."""
    query = db.query(Account).filter(Account.adspower_profile_id.isnot(None))
    if account_ids:
        query = query.filter(Account.id.in_(account_ids))

    accounts = query.all()
    for account in accounts:
        try:
            await randomize_channel_profile(db, account)
            await actions.random_delay(5, 15)
        except Exception as e:
            log.error(f"Profile randomization failed for {account.gmail}: {e}")
