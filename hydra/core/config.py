"""Global configuration loaded from .env"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = {"env_file": ROOT_DIR / ".env", "extra": "ignore"}

    # Claude API
    claude_api_key: str = ""

    # YouTube Data API (rotation)
    youtube_api_key_1: str = ""
    youtube_api_key_2: str = ""

    # 2Captcha
    twocaptcha_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # AdsPower
    adspower_api_url: str = "http://local.adspower.net:50325"
    adspower_api_key: str = ""

    # DB
    db_url: str = Field(default=f"sqlite:///{ROOT_DIR / 'data' / 'hydra.db'}")

    # Paths
    log_dir: Path = ROOT_DIR / "logs"
    data_dir: Path = ROOT_DIR / "data"
    backup_dir: Path = ROOT_DIR / "data" / "backup"

    # Behavior engine defaults
    weekly_promo_comments: int = 70
    weekly_non_promo_actions: int = 140
    daily_max_promo: int = 25
    day_off_probability: float = 0.10
    weekend_boost: float = 1.2

    # Cooldowns
    same_task_same_video_days: int = 7
    session_gap_hours: int = 2
    ghost_cooldown_days: int = 7

    # Backup
    backup_interval_hours: int = 4
    backup_retention_days: int = 7

    @property
    def youtube_api_keys(self) -> list[str]:
        return [k for k in [self.youtube_api_key_1, self.youtube_api_key_2] if k]


settings = Settings()
