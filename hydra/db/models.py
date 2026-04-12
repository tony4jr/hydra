"""
HYDRA Database Models — 11 Tables
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, JSON,
    ForeignKey, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    recovery_email = Column(String)
    phone_number = Column(String)
    totp_secret = Column(String)

    adspower_profile_id = Column(String)
    cookies = Column(Text)

    status = Column(String, nullable=False, default="registered")
    warmup_group = Column(String)
    warmup_start_date = Column(DateTime)
    warmup_end_date = Column(DateTime)
    ghost_count = Column(Integer, default=0)

    persona = Column(JSON)
    role_preference = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime)
    retired_at = Column(DateTime)
    retired_reason = Column(String)
    notes = Column(Text)

    campaign_steps = relationship("CampaignStep", back_populates="account")
    action_logs = relationship("ActionLog", back_populates="account")

    __table_args__ = (
        Index("idx_accounts_status", "status"),
        Index("idx_accounts_warmup", "warmup_group", "status"),
    )


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    product_category = Column(String)
    core_message = Column(Text)
    brand_story = Column(Text)

    target_keywords = Column(JSON)
    allowed_keywords = Column(JSON)
    banned_keywords = Column(JSON)
    ingredients = Column(JSON)
    selling_points = Column(JSON)

    mention_rules = Column(JSON)
    tone_guide = Column(Text)
    target_audience = Column(String)

    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    keywords = relationship("Keyword", back_populates="brand")
    campaigns = relationship("Campaign", back_populates="brand")


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"))
    source = Column(String, default="manual")
    status = Column(String, default="active")
    priority = Column(Integer, default=5)

    total_videos_found = Column(Integer, default=0)
    total_comments_posted = Column(Integer, default=0)
    last_searched_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    brand = relationship("Brand", back_populates="keywords")
    videos = relationship("Video", back_populates="keyword")

    __table_args__ = (
        Index("idx_keywords_status", "status"),
        Index("idx_keywords_brand", "brand_id"),
    )


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
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

    collected_at = Column(DateTime, default=datetime.utcnow)
    last_worked_at = Column(DateTime)

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
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    scenario = Column(String, nullable=False)

    status = Column(String, default="planning")
    like_boost_preset = Column(String)
    like_boost_config = Column(JSON)

    ghost_check_status = Column(String)
    ghost_checked_by = Column(Integer)
    ghost_checked_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

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

    role = Column(String, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String, nullable=False)

    content = Column(Text)
    parent_step_id = Column(Integer, ForeignKey("campaign_steps.id"))
    youtube_comment_id = Column(String)

    scheduled_at = Column(DateTime)
    status = Column(String, default="pending")
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

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
    target_step_id = Column(Integer, ForeignKey("campaign_steps.id"), nullable=False)

    wave_number = Column(Integer, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    scheduled_at = Column(DateTime)
    status = Column(String, default="pending")
    surrounding_likes_count = Column(Integer, default=0)
    completed_at = Column(DateTime)

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

    ip_address = Column(String)
    duration_sec = Column(Integer)

    status = Column(String, default="success")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

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

    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)

    __table_args__ = (
        Index("idx_ip_account", "account_id"),
        Index("idx_ip_address", "ip_address", "started_at"),
    )


class WeeklyGoal(Base):
    __tablename__ = "weekly_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    week_start = Column(String, nullable=False)

    promo_target = Column(Integer, default=70)
    promo_done = Column(Integer, default=0)
    non_promo_target = Column(Integer, default=140)
    non_promo_done = Column(Integer, default=0)


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ErrorLog(Base):
    __tablename__ = "error_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, nullable=False)
    source = Column(String)
    account_id = Column(Integer)
    video_id = Column(String)
    campaign_id = Column(Integer)

    message = Column(Text, nullable=False)
    stack_trace = Column(Text)

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_error_level", "level", "created_at"),
        Index("idx_error_source", "source"),
    )
