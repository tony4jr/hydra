"""SQLAlchemy models — 15 tables (12 spec + 3 from MKT_TUBE analysis)."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    recovery_email = Column(String)
    phone_number = Column(String)
    totp_secret = Column(String)

    adspower_profile_id = Column(String)
    youtube_channel_id = Column(String)
    cookies = Column(Text)  # JSON (encrypted)

    status = Column(String, nullable=False, default="registered")
    warmup_group = Column(String)  # A~E
    warmup_start_date = Column(DateTime)
    warmup_end_date = Column(DateTime)

    ghost_count = Column(Integer, default=0)

    persona = Column(Text)  # JSON
    role_preference = Column(String)  # seed|witness|agree|any

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_active_at = Column(DateTime)
    retired_at = Column(DateTime)
    retired_reason = Column(String)
    notes = Column(Text)

    daily_comment_limit = Column(Integer, default=15)
    daily_like_limit = Column(Integer, default=50)
    weekly_comment_limit = Column(Integer, default=70)
    weekly_like_limit = Column(Integer, default=300)

    # relationships
    campaign_steps = relationship("CampaignStep", back_populates="account")
    action_logs = relationship("ActionLog", back_populates="account")
    weekly_goals = relationship("WeeklyGoal", back_populates="account")

    __table_args__ = (
        Index("idx_accounts_status", "status"),
        Index("idx_accounts_warmup", "warmup_group", "status"),
        UniqueConstraint("adspower_profile_id", name="uq_accounts_adspower_profile_id"),
    )


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    product_category = Column(String)
    core_message = Column(Text)
    brand_story = Column(Text)

    target_keywords = Column(Text)   # JSON
    allowed_keywords = Column(Text)  # JSON
    banned_keywords = Column(Text)   # JSON
    ingredients = Column(Text)       # JSON
    selling_points = Column(Text)    # JSON

    promo_keywords = Column(Text)    # JSON — 홍보 키워드 (댓글에 녹일 메시지)
    selected_presets = Column(Text)  # JSON — 사용할 프리셋 코드 목록 ["A","B","C"]

    mention_rules = Column(Text)  # JSON
    tone_guide = Column(Text)
    target_audience = Column(String)

    weekly_campaign_target = Column(Integer, default=0)
    auto_campaign_enabled = Column(Boolean, default=False)

    status = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # relationships
    keywords = relationship("Keyword", back_populates="brand")
    campaigns = relationship("Campaign", back_populates="brand")


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"))
    source = Column(String, default="manual")   # manual|auto_expanded|trending
    status = Column(String, default="active")    # active|paused|excluded
    priority = Column(Integer, default=5)

    total_videos_found = Column(Integer, default=0)
    total_comments_posted = Column(Integer, default=0)
    last_searched_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # relationships
    brand = relationship("Brand", back_populates="keywords")
    videos = relationship("Video", back_populates="keyword")

    __table_args__ = (
        Index("idx_keywords_status", "status"),
        Index("idx_keywords_brand", "brand_id"),
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)  # YouTube video ID
    url = Column(String, nullable=False)
    title = Column(String)
    channel_id = Column(String)
    channel_title = Column(String)
    description = Column(Text)

    view_count = Column(Integer)
    like_count = Column(Integer)
    comment_count = Column(Integer)
    duration_sec = Column(Integer)
    published_at = Column(DateTime)

    is_short = Column(Boolean, default=False)
    has_subtitles = Column(Boolean)
    comments_enabled = Column(Boolean, default=True)

    status = Column(String, default="available")
    keyword_id = Column(Integer, ForeignKey("keywords.id"))
    priority = Column(String, default="normal")

    collected_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_worked_at = Column(DateTime)

    # relationships
    keyword = relationship("Keyword", back_populates="videos")
    campaigns = relationship("Campaign", back_populates="video")

    __table_args__ = (
        Index("idx_videos_status", "status"),
        Index("idx_videos_priority", "priority"),
        Index("idx_videos_published", "published_at"),
        Index("idx_videos_keyword", "keyword_id"),
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    scenario = Column(String, nullable=False)  # A~J

    status = Column(String, default="planning")
    like_boost_preset = Column(String)   # conservative|normal|aggressive|custom
    like_boost_config = Column(Text)     # JSON

    ghost_check_status = Column(String)  # pending|visible|ghost|unchecked
    ghost_checked_by = Column(Integer)
    ghost_checked_at = Column(DateTime)

    campaign_type = Column(String, default="scenario")
    comment_mode = Column(String, default="ai_auto")
    preset_id = Column(Integer, ForeignKey("presets.id"))
    user_id = Column(Integer)

    # UI/UX 재설계 — 캠페인이 작업의 모든 것을 관리
    name = Column(String)                         # 캠페인 이름 (예: "트리코라 — 탈모 캠페인")
    target_keywords = Column(Text)                # JSON — 타겟 키워드 (영상 검색용)
    mention_style = Column(Text)                  # 제품 언급 방식
    selected_presets = Column(Text)               # JSON — 사용할 프리셋 코드 목록
    sets_per_video = Column(Integer, default=1)   # 영상당 프리셋 세트 수
    duration_days = Column(Integer)               # 작업 기간 (일)
    target_count = Column(Integer)                # 목표 영상 수
    start_date = Column(DateTime)                 # 시작일
    end_date = Column(DateTime)                   # 종료일

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    completed_at = Column(DateTime)

    # relationships
    video = relationship("Video", back_populates="campaigns")
    brand = relationship("Brand", back_populates="campaigns")
    steps = relationship("CampaignStep", back_populates="campaign")
    like_boosts = relationship("LikeBoostQueue", back_populates="campaign")

    __table_args__ = (
        Index("idx_campaigns_status", "status"),
        Index("idx_campaigns_video", "video_id"),
    )


class CampaignStep(Base):
    __tablename__ = "campaign_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    step_number = Column(Integer, nullable=False)

    role = Column(String, nullable=False)     # seed|asker|witness|agree|...
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String, nullable=False)     # comment|reply|like|like_boost

    content = Column(Text)
    parent_step_id = Column(Integer)
    youtube_comment_id = Column(String)

    scheduled_at = Column(DateTime)
    status = Column(String, default="pending")
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # relationships
    campaign = relationship("Campaign", back_populates="steps")
    account = relationship("Account", back_populates="campaign_steps")

    __table_args__ = (
        Index("idx_steps_campaign", "campaign_id"),
        Index("idx_steps_status", "status", "scheduled_at"),
        Index("idx_steps_account", "account_id"),
    )


class LikeBoostQueue(Base):
    __tablename__ = "like_boost_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    target_step_id = Column(Integer, nullable=False)

    wave_number = Column(Integer, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    scheduled_at = Column(DateTime)
    status = Column(String, default="pending")
    surrounding_likes_count = Column(Integer, default=0)
    completed_at = Column(DateTime)

    # relationships
    campaign = relationship("Campaign", back_populates="like_boosts")

    __table_args__ = (
        Index("idx_like_queue_status", "status", "scheduled_at"),
    )


class ActionLog(Base):
    __tablename__ = "action_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    video_id = Column(String)
    campaign_id = Column(Integer)

    action_type = Column(String, nullable=False)
    is_promo = Column(Boolean, default=False)
    content = Column(Text)
    youtube_comment_id = Column(String)  # for comment tracking/survival check
    session_id = Column(String)          # group actions in same session

    ip_address = Column(String)
    duration_sec = Column(Integer)

    status = Column(String, default="success")
    error_message = Column(Text)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # relationships
    account = relationship("Account", back_populates="action_logs")

    __table_args__ = (
        Index("idx_action_video", "video_id", "action_type"),
        Index("idx_action_account", "account_id", "created_at"),
        Index("idx_action_date", "created_at"),
    )


class IpLog(Base):
    __tablename__ = "ip_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    ip_address = Column(String, nullable=False)
    device_id = Column(String)

    started_at = Column(DateTime, default=lambda: datetime.now(UTC))
    ended_at = Column(DateTime)

    __table_args__ = (
        Index("idx_ip_account", "account_id"),
        Index("idx_ip_address", "ip_address", "started_at"),
    )


class WeeklyGoal(Base):
    __tablename__ = "weekly_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    week_start = Column(DateTime, nullable=False)

    promo_target = Column(Integer, default=70)
    promo_done = Column(Integer, default=0)
    non_promo_target = Column(Integer, default=140)
    non_promo_done = Column(Integer, default=0)

    # relationships
    account = relationship("Account", back_populates="weekly_goals")

    __table_args__ = (
        UniqueConstraint("account_id", "week_start"),
    )


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC))


class ErrorLog(Base):
    __tablename__ = "error_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, nullable=False)   # info|warning|error|critical
    source = Column(String)                  # chrome|youtube|claude|ip|system
    account_id = Column(Integer)
    video_id = Column(String)
    campaign_id = Column(Integer)

    message = Column(Text, nullable=False)
    stack_trace = Column(Text)

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_error_level", "level", "created_at"),
        Index("idx_error_source", "source"),
    )


# --- MKT_TUBE-derived tables ---

class ScrapedComment(Base):
    """Real YouTube comments scraped for AI training dataset."""
    __tablename__ = "scraped_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False)
    author_name = Column(String)
    author_channel = Column(String)
    content = Column(Text, nullable=False)
    content_hash = Column(String, unique=True)  # dedup
    like_count = Column(Integer, default=0)
    time_text = Column(String)  # "2주 전" etc.

    scraped_at = Column(DateTime, default=lambda: datetime.now(UTC))
    used_for_training = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_scraped_video", "video_id"),
        Index("idx_scraped_likes", "like_count"),
    )


class ProfilePool(Base):
    """Pool of randomizable profile assets (avatar, banner, name, etc.).

    MKT_TUBE ChangeInfoChannels pattern: load pool → random select → apply.
    """
    __tablename__ = "profile_pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_type = Column(String, nullable=False)  # avatar|banner|name|description|contact|hashtag
    content = Column(Text, nullable=False)       # file path or text content
    used_count = Column(Integer, default=0)
    last_used_at = Column(DateTime)
    disabled = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_pool_type", "pool_type", "disabled"),
    )


class ChannelProfileHistory(Base):
    """Log of channel profile changes for each account."""
    __tablename__ = "channel_profile_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    avatar_path = Column(String)
    banner_path = Column(String)
    name = Column(String)
    description = Column(Text)
    contact = Column(String)
    hashtags = Column(Text)  # JSON

    applied_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_profile_history_account", "account_id"),
    )


class RecoveryEmail(Base):
    """Pool of real recovery email accounts used for Gmail signup.

    Each Gmail account requires a recovery email. We claim one from this
    pool per signup and use IMAP to fetch Google's verification codes.
    """
    __tablename__ = "recovery_emails"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)  # encrypted (app password for IMAP)
    imap_host = Column(String)                  # e.g. imap.naver.com (auto-detected if empty)
    imap_port = Column(Integer, default=993)

    # Assignment lifecycle
    used_by_account_id = Column(Integer, ForeignKey("accounts.id"))
    used_at = Column(DateTime)
    disabled = Column(Boolean, default=False)   # manually disabled / burned
    last_error = Column(String)                 # latest IMAP / assignment error

    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_recovery_available", "disabled", "used_by_account_id"),
    )


class PersonaSlot(Base):
    """Pre-seeded demographic slots for Korean persona diversity.

    Each slot is claimed once by an account; prevents demographic bias
    when generating personas in bulk. Device_hint bridges Layer 2 (person)
    to Layer 1 (fingerprint).
    """
    __tablename__ = "persona_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)           # male/female
    occupation = Column(String, nullable=False)       # 대학생/회사원/자영업/주부/프리랜서/은퇴/전문직
    region = Column(String, nullable=False)           # 서울/경기/부산/...
    device_hint = Column(String, nullable=False)      # mac_heavy/windows_heavy/windows_10_heavy/mixed

    used = Column(Boolean, default=False, nullable=False)
    assigned_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    used_at = Column(DateTime)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_slot_used", "used"),
        Index("idx_slot_demo", "age", "gender", "occupation"),
    )


# --- v2: Worker / Task / Preset / ProfileLock ---


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    token_hash = Column(String, nullable=False)
    status = Column(String, default="offline")
    allow_preparation = Column(Boolean, default=False)
    allow_campaign = Column(Boolean, default=True)
    ip_method = Column(String, default="adb_mobile")
    ip_config = Column(Text)
    last_heartbeat = Column(DateTime)
    current_version = Column(String)
    os_type = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    notes = Column(Text)

    tasks = relationship("Task", back_populates="worker")

    __table_args__ = (
        Index("idx_workers_status", "status"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    campaign_step_id = Column(Integer, ForeignKey("campaign_steps.id"))
    worker_id = Column(Integer, ForeignKey("workers.id"))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    task_type = Column(String, nullable=False)
    priority = Column(String, default="normal")
    status = Column(String, default="pending")
    payload = Column(Text)
    result = Column(Text)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    scheduled_at = Column(DateTime)
    assigned_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    worker = relationship("Worker", back_populates="tasks")
    campaign = relationship("Campaign")
    account = relationship("Account")

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_worker", "worker_id"),
        Index("idx_tasks_priority_status", "priority", "status"),
        Index("idx_tasks_scheduled", "scheduled_at"),
    )


class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True)
    is_system = Column(Boolean, default=False)
    description = Column(Text)
    steps = Column(Text, nullable=False)
    user_id = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_presets_code", "code"),
    )


class ProfileLock(Base):
    __tablename__ = "profile_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    adspower_profile_id = Column(String, nullable=False)
    locked_at = Column(DateTime, default=lambda: datetime.now(UTC))
    released_at = Column(DateTime)

    account = relationship("Account")
    worker = relationship("Worker")

    __table_args__ = (
        Index("idx_locks_account", "account_id"),
        Index("idx_locks_active", "released_at"),
    )


class AccountProfileHistory(Base):
    __tablename__ = "account_profile_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)
    adspower_profile_id = Column(String, nullable=False)
    fingerprint_snapshot = Column(Text)  # JSON
    created_source = Column(String, nullable=False, default="auto")  # auto | manual_mapped
    device_hint = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    retired_at = Column(DateTime)
    retire_reason = Column(String)

    __table_args__ = (
        Index("idx_profhist_account", "account_id"),
        Index("idx_profhist_active", "account_id", "retired_at"),
    )
