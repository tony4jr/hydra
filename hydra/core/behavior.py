"""Behavior engine — human simulation.

Spec Part 7:
- Weekly goals → daily distribution (gaussian + rest days)
- Session structure (1~4 sessions/day, time slots)
- Action loop (scroll, search, watch, shorts, end)
- Watch duration distribution
"""

import random
import math
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta

from hydra.core.config import settings

# Korean Standard Time (UTC+9)
KST = timezone(timedelta(hours=9))


@dataclass
class SessionPlan:
    start_hour: int
    start_minute: int
    duration_minutes: int
    slot: str  # morning | lunch | evening | night


@dataclass
class DailyPlan:
    sessions: list[SessionPlan]
    promo_target: int
    non_promo_target: int
    is_rest_day: bool


# Time slots (spec 7.2)
SLOTS = {
    "morning": {"start": 8, "end": 10, "dur_min": 15, "dur_max": 30},
    "lunch":   {"start": 12, "end": 14, "dur_min": 20, "dur_max": 40},
    "evening": {"start": 19, "end": 23, "dur_min": 30, "dur_max": 90},
    "night":   {"start": 0, "end": 1, "dur_min": 10, "dur_max": 20},
}

# Session count weights (spec 7.2)
SESSION_COUNT_WEIGHTS = [20, 35, 30, 15]  # 1~4 sessions

# Action weights (spec 7.3)
ACTION_WEIGHTS = {
    "home_scroll": 0.25,
    "keyword_search": 0.20,
    "recommended": 0.25,
    "shorts": 0.15,
    "end_session": 0.15,
}

# Watch duration distribution (spec 7.4)
WATCH_DISTRIBUTION = {
    "instant_exit": (0.15, 1, 3),      # weight, min_sec, max_sec
    "short":        (0.25, 5, 30),
    "medium":       (0.30, 30, 180),
    "long":         (0.20, 180, 600),
    "full":         (0.10, 600, 1800),
}


def plan_daily(
    promo_remaining: int,
    non_promo_remaining: int,
    days_left: int,
    is_weekend: bool = False,
) -> DailyPlan:
    """Generate daily activity plan for an account.

    Spec 7.1: gaussian distribution with variance.
    """
    # Rest day?
    if random.random() < settings.day_off_probability:
        return DailyPlan(
            sessions=[],
            promo_target=random.randint(0, 3),
            non_promo_target=random.randint(0, 5),
            is_rest_day=True,
        )

    # Daily target (gaussian)
    if days_left > 0:
        avg_promo = promo_remaining / days_left
        avg_non_promo = non_promo_remaining / days_left
    else:
        avg_promo = min(promo_remaining, settings.daily_max_promo)
        avg_non_promo = min(non_promo_remaining, 40)

    promo_today = max(0, int(random.gauss(avg_promo, avg_promo * 0.4)))
    non_promo_today = max(0, int(random.gauss(avg_non_promo, avg_non_promo * 0.4)))

    # Weekend boost
    if is_weekend:
        promo_today = int(promo_today * settings.weekend_boost)
        non_promo_today = int(non_promo_today * settings.weekend_boost)

    # Catch-up if behind
    if days_left <= 2 and promo_remaining > avg_promo * 2:
        promo_today = min(promo_remaining // max(days_left, 1), settings.daily_max_promo)

    # Clamp
    promo_today = min(promo_today, settings.daily_max_promo)

    # Plan sessions
    num_sessions = random.choices([1, 2, 3, 4], weights=SESSION_COUNT_WEIGHTS)[0]
    slot_names = list(SLOTS.keys())
    chosen_slots = random.sample(slot_names, min(num_sessions, len(slot_names)))
    chosen_slots.sort(key=lambda s: SLOTS[s]["start"])

    sessions = []
    for slot_name in chosen_slots:
        slot = SLOTS[slot_name]
        start_h = random.randint(slot["start"], max(slot["start"], slot["end"] - 1))
        start_m = random.randint(0, 59)
        duration = random.randint(slot["dur_min"], slot["dur_max"])
        sessions.append(SessionPlan(
            start_hour=start_h,
            start_minute=start_m,
            duration_minutes=duration,
            slot=slot_name,
        ))

    return DailyPlan(
        sessions=sessions,
        promo_target=promo_today,
        non_promo_target=non_promo_today,
        is_rest_day=False,
    )


def pick_action() -> str:
    """Pick next action in a session. Spec 7.3."""
    actions = list(ACTION_WEIGHTS.keys())
    weights = list(ACTION_WEIGHTS.values())
    return random.choices(actions, weights=weights)[0]


def pick_watch_duration() -> int:
    """Pick how long to watch a video (seconds). Spec 7.4."""
    categories = list(WATCH_DISTRIBUTION.values())
    weights = [c[0] for c in categories]
    chosen = random.choices(categories, weights=weights)[0]
    _, min_sec, max_sec = chosen
    return random.randint(min_sec, max_sec)


def should_comment_promo(promo_remaining: int) -> bool:
    """Decide if we should leave a promo comment after watching. Spec 7.4."""
    if promo_remaining <= 0:
        return False
    return random.random() < 0.60


def should_comment_non_promo(non_promo_remaining: int) -> bool:
    """Decide if we should leave a non-promo comment/like."""
    if non_promo_remaining <= 0:
        return False
    return random.random() < 0.30


def is_natural_activity_hour() -> bool:
    """Check if current KST hour is within natural YouTube activity hours.

    Natural hours: 07:00 ~ 01:00 KST (avoid 01~07 = sleeping).
    """
    kst_now = datetime.now(KST)
    hour = kst_now.hour
    return hour >= 7 or hour < 1


def seconds_until_natural_hour() -> int:
    """Seconds until the next natural activity window opens (07:00 KST)."""
    kst_now = datetime.now(KST)
    if is_natural_activity_hour():
        return 0
    # Currently 01:00~06:59 → wait until 07:00
    next_start = kst_now.replace(hour=7, minute=0, second=0, microsecond=0)
    if kst_now.hour >= 7:
        next_start += timedelta(days=1)
    return int((next_start - kst_now).total_seconds())


def get_current_slot() -> str | None:
    """Get the current time slot name based on KST, or None if outside slots."""
    kst_now = datetime.now(KST)
    hour = kst_now.hour
    for name, slot in SLOTS.items():
        if slot["start"] <= hour < slot["end"]:
            return name
        # Handle night slot wrapping (0~1)
        if name == "night" and hour < slot["end"]:
            return name
    return None


def pick_typing_method() -> str:
    """Choose paste vs char-by-char. Spec 7.5."""
    return "paste" if random.random() < 0.80 else "type"


def pick_ad_behavior() -> str:
    """Choose how to handle a YouTube ad. Spec 7.4."""
    roll = random.random()
    if roll < 0.60:
        return "skip"
    elif roll < 0.85:
        return "watch"
    else:
        return "back"
