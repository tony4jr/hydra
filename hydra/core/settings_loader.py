"""Load settings from DB (system_config) and apply to behavior engine.

UI에서 Settings 저장 → DB → 이 모듈이 엔진에 반영.
"""

from sqlalchemy.orm import Session

from hydra.core.logger import get_logger
from hydra.core import behavior
from hydra.db.models import SystemConfig

log = get_logger("settings_loader")


def load_and_apply(db: Session):
    """Read all system_config rows and apply to behavior engine."""
    rows = db.query(SystemConfig).all()
    config = {r.key: r.value for r in rows}

    # Behavior engine
    if "behavior.weekly_promo_comments" in config:
        from hydra.core.config import settings
        settings.weekly_promo_comments = int(config["behavior.weekly_promo_comments"])
    if "behavior.weekly_non_promo_actions" in config:
        from hydra.core.config import settings
        settings.weekly_non_promo_actions = int(config["behavior.weekly_non_promo_actions"])
    if "behavior.daily_max_promo" in config:
        from hydra.core.config import settings
        settings.daily_max_promo = int(config["behavior.daily_max_promo"])
    if "behavior.day_off_probability" in config:
        from hydra.core.config import settings
        settings.day_off_probability = float(config["behavior.day_off_probability"])
    if "behavior.weekend_boost" in config:
        from hydra.core.config import settings
        settings.weekend_boost = float(config["behavior.weekend_boost"])

    # Session weights
    w = []
    for i in range(1, 5):
        key = f"behavior.session_{i}_weight"
        w.append(int(config.get(key, behavior.SESSION_COUNT_WEIGHTS[i-1])))
    if w:
        behavior.SESSION_COUNT_WEIGHTS[:] = w

    # Action weights
    action_map = {
        "behavior.action_home_scroll": "home_scroll",
        "behavior.action_keyword_search": "keyword_search",
        "behavior.action_recommended": "recommended",
        "behavior.action_shorts": "shorts",
        "behavior.action_end_session": "end_session",
    }
    for cfg_key, action_key in action_map.items():
        if cfg_key in config:
            behavior.ACTION_WEIGHTS[action_key] = int(config[cfg_key]) / 100.0

    # Cooldowns
    if "cooldown.ghost_cooldown_days" in config:
        from hydra.core.config import settings
        settings.ghost_cooldown_days = int(config["cooldown.ghost_cooldown_days"])
    if "cooldown.session_gap_hours" in config:
        from hydra.core.config import settings
        settings.session_gap_hours = int(config["cooldown.session_gap_hours"])

    log.info(f"Settings loaded from DB ({len(config)} keys)")
