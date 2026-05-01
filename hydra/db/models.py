"""SQLAlchemy models — 15 tables (12 spec + 3 from MKT_TUBE analysis)."""

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint,
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
    warmup_day = Column(Integer, nullable=False, default=0)  # 0=미시작, 1~3=진행, >3=졸업
    onboard_completed_at = Column(DateTime)

    ghost_count = Column(Integer, default=0)

    # 본인 인증 챌린지 — 실패 시 7일 쿨다운. 반복되면 밴 후보.
    identity_challenge_until = Column(DateTime)  # 이 시각 이전엔 태스크 배정 금지
    identity_challenge_count = Column(Integer, default=0)

    # ipp (복구 전화 변경 확인) 우회한 계정 — Google 계정 설정 수정 불가.
    # 워밍업/댓글은 YT 도메인 내에서만 진행하도록 워커가 체크.
    ipp_flagged = Column(Boolean, default=False, nullable=False)

    # D 단계(외부 고객 포털) 대비 — 현재 NULL (내부 소유). Phase 1~C 사용 안 함.
    customer_id = Column(Integer, nullable=True)

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

    # 영상 수집 정책 (Smart Pickup)
    collection_depth = Column(String(20), default="standard")  # quick|standard|deep|max
    longtail_count = Column(Integer, default=5)  # 키워드당 자동 생성할 변형 수
    scoring_weights = Column(Text)  # JSON: {freshness, popularity, untouched, random}
    preset_video_limit = Column(Integer, default=1)  # 같은 영상에 같은 프리셋 몇 회까지

    status = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # relationships
    keywords = relationship("Keyword", back_populates="brand")
    campaigns = relationship("Campaign", back_populates="brand")
    niches = relationship("Niche", back_populates="brand", cascade="all, delete-orphan")


class Niche(Base):
    """시장 (Niche) — Brand 1:N Niche.

    PR-3: Brand 1계층 → Brand → Niche 2계층 확장.
    이전엔 Brand 가 시장 정의 (embedding_reference_text 등) + 정책을 모두 가졌음.
    Niche 가 흡수 (점진 마이그레이션, Brand fallback 가능).

    출처 (spec PR-3 컬럼 매핑):
    - market_definition          ← TargetCollectionConfig.embedding_reference_text
    - embedding_threshold        ← TargetCollectionConfig.embedding_threshold
    - trending_vph_threshold     ← TargetCollectionConfig.l3_views_per_hour_threshold
    - long_term_score_threshold  ← TargetCollectionConfig.l1_threshold_score
    - new_video_hours            ← 신규 도입 (default 6)
    - collection_depth           ← Brand.collection_depth
    - keyword_variation_count    ← Brand.longtail_count
    - preset_per_video_limit     ← Brand.preset_video_limit
    """
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(Text)

    # 시장 정의 (이전: TargetCollectionConfig)
    market_definition = Column(Text)
    embedding_threshold = Column(Float, default=0.65, nullable=False)

    # 우선순위 임계값
    trending_vph_threshold = Column(Integer, default=1000, nullable=False)
    new_video_hours = Column(Integer, default=6, nullable=False)
    long_term_score_threshold = Column(Integer, default=70, nullable=False)

    # 수집 깊이 정책 (이전: Brand)
    collection_depth = Column(String(20), default="standard", nullable=False)  # quick|standard|deep|max
    keyword_variation_count = Column(Integer, default=5, nullable=False)
    preset_per_video_limit = Column(Integer, default=1, nullable=False)

    # 상태
    state = Column(String(20), default="active", nullable=False)  # active|paused|archived

    # PR-4d — 메시지 탭 (Brand → Niche 이전, default Niche 백필)
    core_message = Column(Text)
    tone_guide = Column(Text)
    target_audience = Column(String(200))
    mention_rules = Column(Text)  # JSON
    personas_json = Column(Text)  # JSON list, max 10 슬롯
    promotional_keywords = Column(Text)  # JSON list
    preset_selection = Column(Text)  # JSON list of preset codes

    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC), nullable=False)

    # relationships
    brand = relationship("Brand", back_populates="niches")
    keywords = relationship("Keyword", back_populates="niche")
    campaigns = relationship("Campaign", back_populates="niche")

    __table_args__ = (
        Index("ix_niches_brand_state", "brand_id", "state"),
    )


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    text = Column(String, nullable=False)
    brand_id = Column(Integer, ForeignKey("brands.id"))
    niche_id = Column(Integer, ForeignKey("niches.id", ondelete="SET NULL"), nullable=True)  # PR-3
    source = Column(String, default="manual")   # manual|auto_expanded|trending
    status = Column(String, default="active")    # active|paused|excluded
    priority = Column(Integer, default=5)

    total_videos_found = Column(Integer, default=0)
    total_comments_posted = Column(Integer, default=0)
    last_searched_at = Column(DateTime)

    # Long-tail 변형 추적
    parent_keyword_id = Column(Integer, ForeignKey("keywords.id", ondelete="SET NULL"))
    is_variant = Column(Boolean, default=False)

    # Phase 1 — 키워드 tier + 폴링 빈도
    keyword_tier = Column(String(20), default="core")  # core|expansion|long_tail
    is_negative = Column(Boolean, default=False)  # 부정 키워드 (배제 룰)
    poll_5min = Column(Boolean, default=False)  # 핫 키워드만 (운영자가 명시 활성화)
    poll_30min = Column(Boolean, default=False)
    poll_daily = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

    # relationships
    brand = relationship("Brand", back_populates="keywords")
    niche = relationship("Niche", back_populates="keywords")
    videos = relationship("Video", back_populates="keyword")
    parent = relationship("Keyword", remote_side="Keyword.id", backref="variants")

    __table_args__ = (
        Index("idx_keywords_status", "status"),
        Index("idx_keywords_brand", "brand_id"),
        Index("idx_keywords_niche", "niche_id"),
        Index("idx_keywords_parent", "parent_keyword_id"),
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
    niche_id = Column(Integer, ForeignKey("niches.id", ondelete="SET NULL"), nullable=True)  # PR-3
    priority = Column(String, default="normal")

    collected_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_worked_at = Column(DateTime)

    # Smart Pickup 메타
    total_campaigns_count = Column(Integer, default=0)
    popularity_score = Column(Float)  # nightly 배치로 갱신
    discovered_via = Column(String(50))  # search_viewCount|search_date|search_relevance|longtail|manual
    discovery_keyword = Column(String(200))  # 발견 시 사용된 keyword/variant 텍스트

    # Phase 1 — L 티어 + Lifecycle Phase + state
    l_tier = Column(String(2))  # L1|L2|L3|L4
    lifecycle_phase = Column(SmallInteger)  # 1=신규(7일)|2=안정화(~1m)|3=에버그린(~6m)|4=장기
    category_subtype = Column(String(50))  # Phase 2 LLM 분류
    embedding_score = Column(Float)  # 0~1 (Phase 1 임베딩 분류)
    our_presence_score = Column(Float, default=0)
    total_scenarios_run = Column(Integer, default=0)
    last_action_at = Column(DateTime)
    next_revisit_at = Column(DateTime)
    state = Column(String(20), default="pending")  # pending|active|paused|completed|blacklisted
    blacklist_reason = Column(String(100))
    top_comment_likes = Column(Integer, default=0)  # 베스트댓글 진입성 점수용
    view_count_prev_day = Column(Integer, default=0)
    views_per_hour_recent = Column(Float, default=0)
    relevance_score_v2 = Column(Float)  # Phase 2 5점수 합산 (popularity_score 와 별개)

    # relationships
    keyword = relationship("Keyword", back_populates="videos")
    campaigns = relationship("Campaign", back_populates="video")

    __table_args__ = (
        Index("idx_videos_status", "status"),
        Index("idx_videos_priority", "priority"),
        Index("idx_videos_published", "published_at"),
        Index("idx_videos_keyword", "keyword_id"),
        Index("idx_videos_last_worked", "last_worked_at"),
        Index("idx_videos_popularity", "popularity_score"),
        Index("idx_videos_l_tier", "l_tier"),
        Index("idx_videos_state", "state"),
        Index("idx_videos_next_revisit", "next_revisit_at"),
        Index("idx_videos_lifecycle", "lifecycle_phase"),
        Index("idx_videos_collected_at", "collected_at"),
        Index("idx_videos_niche", "niche_id"),
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    niche_id = Column(Integer, ForeignKey("niches.id", ondelete="SET NULL"), nullable=True)  # PR-3
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

    # D 단계(외부 고객 포털) 대비
    customer_id = Column(Integer, nullable=True)

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
    niche = relationship("Niche", back_populates="campaigns")
    steps = relationship("CampaignStep", back_populates="campaign")
    like_boosts = relationship("LikeBoostQueue", back_populates="campaign")

    __table_args__ = (
        Index("idx_campaigns_status", "status"),
        Index("idx_campaigns_video", "video_id"),
        Index("idx_campaigns_niche", "niche_id"),
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
    token_hash = Column(String, nullable=True)  # [LEGACY] bcrypt — 점진적 폐기
    # [LEGACY] 8자 prefix — token_sha256 도입 전 중간 단계. 제거 예정.
    token_prefix = Column(String(8), nullable=True, index=True)
    # [PRIMARY] SHA-256(raw_token) hex — UNIQUE 인덱스로 O(1) auth.
    # 워커 토큰은 256bit 랜덤이라 bcrypt 불필요 (brute force 불가).
    token_sha256 = Column(String(64), nullable=True, unique=True, index=True)
    # 워커 전용 비밀 — 서버 Fernet 암호화 저장. heartbeat 응답으로 복호화 전달.
    # AdsPower Local API 키는 머신마다 다를 수 있어 워커별 저장.
    adspower_api_key_enc = Column(Text, nullable=True)
    status = Column(String, default="offline")
    allow_preparation = Column(Boolean, default=False)
    allow_campaign = Column(Boolean, default=True)
    ip_method = Column(String, default="adb_mobile")
    ip_config = Column(Text)
    last_heartbeat = Column(DateTime)
    current_version = Column(String)
    os_type = Column(String)
    enrolled_at = Column(DateTime)
    health_snapshot = Column(Text)  # JSON 문자열
    tailscale_ip = Column(String(45))
    allowed_task_types = Column(Text, nullable=False, default='["*"]', server_default='["*"]')
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    notes = Column(Text)
    # T7 Circuit Breaker — 연속 실패 카운터
    consecutive_failures = Column(Integer, nullable=False, default=0, server_default='0')
    last_failure_at = Column(DateTime, nullable=True)
    paused_reason = Column(String(255), nullable=True)  # circuit-breaker / manual / emergency-stop

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

    # D 단계(외부 고객 포털) 대비
    customer_id = Column(Integer, nullable=True)

    worker = relationship("Worker", back_populates="tasks")
    campaign = relationship("Campaign")
    account = relationship("Account")

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_worker", "worker_id"),
        Index("idx_tasks_priority_status", "priority", "status"),
        Index("idx_tasks_scheduled", "scheduled_at"),
        Index("idx_tasks_created_at", "created_at"),
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
    """계정-워커-태스크 동시 실행 방지 락.

    원래 account 와 worker 만 관리하던 것을 task_id 도 추적.
    DB 레벨 UNIQUE partial index (account_id WHERE released_at IS NULL) 로
    한 account 에 active lock 1개만 보장 → 동시 실행 원천 차단.
    """
    __tablename__ = "profile_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    adspower_profile_id = Column(String, nullable=False)
    locked_at = Column(DateTime, default=lambda: datetime.now(UTC))
    released_at = Column(DateTime)

    account = relationship("Account")
    worker = relationship("Worker")

    __table_args__ = (
        Index("idx_locks_account", "account_id"),
        Index("idx_locks_active", "released_at"),
        # 'idx_profile_locks_active' UNIQUE partial index 는 마이그레이션에서 raw SQL 로 생성
        # (SQLAlchemy Index 는 partial WHERE 직접 지원이 dialect 의존적이라 raw 사용)
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


class User(Base):
    """어드민 로그인 — bcrypt 해시된 비밀번호 + 역할 기반 권한.

    Phase 1 에선 admin / operator 만 사용. customer 는 D 단계 대비.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="operator")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    last_login_at = Column(DateTime, nullable=True)


class ExecutionLog(Base):
    """워커가 태스크 실행 중 중앙 VPS 로 업로드하는 실행 로그.

    - 하루 수천~수만 row 예상 → 30일 주기 auto-delete (Phase 4)
    - task_id ON DELETE CASCADE: task 삭제 시 관련 로그 자동 정리
    - context 는 JSON (url, selector, step 등 구조화 메타데이터)
    """
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    timestamp = Column(DateTime, nullable=False)
    level = Column(String(16), nullable=False)        # DEBUG / INFO / WARN / ERROR
    message = Column(Text, nullable=False)
    context = Column(Text, nullable=True)             # JSON
    screenshot_url = Column(String(512), nullable=True)

    __table_args__ = (
        Index("idx_exec_task", "task_id"),
        Index("idx_exec_worker_time", "worker_id", "timestamp"),
        Index("idx_exec_account_time", "account_id", "timestamp"),
    )


class CampaignVideo(Base):
    """T17 — 캠페인이 여러 영상을 타겟팅 (1:N).

    기존 Campaign.video_id 는 단일 영상용 — 호환 유지.
    캠페인이 다영상 모드면 campaign_videos 가 진실, video_id 는 NULL 가능.

    각 row 는 캠페인이 그 영상에 대해 수행할 작업의 메타:
    - target_count: 그 영상에 댓글 N개 (다계정 분배)
    - completed_count: 진행 진척도
    - funnel_stage: 인지/고려/전환/리텐션 (퍼널 단계)
    """
    __tablename__ = "campaign_videos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    funnel_stage = Column(String(32), nullable=True)  # awareness|consideration|conversion|retention
    target_count = Column(Integer, nullable=False, default=1)
    completed_count = Column(Integer, nullable=False, default=0)
    priority = Column(Integer, nullable=False, default=0)  # 정렬 우선순위
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("campaign_id", "video_id", name="uq_campaign_video"),
        Index("idx_cvideo_campaign", "campaign_id"),
        Index("idx_cvideo_video", "video_id"),
    )


class WorkerCommand(Base):
    """어드민이 워커에게 발행하는 원격 명령.

    흐름: admin POST /command → DB insert (status=pending) →
          워커 heartbeat 응답에 pending_commands 포함 →
          워커 실행 후 POST /ack → status=done|failed.

    timeout: pending 상태 10분 초과 시 별도 배치가 status=timeout 마킹 (옵션).
    """
    __tablename__ = "worker_commands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    command = Column(String(64), nullable=False)  # restart / update_now / run_diag 등
    payload = Column(Text, nullable=True)         # JSON 문자열 (선택)
    status = Column(String(16), nullable=False, default="pending")
    # pending → delivered → done | failed | timeout
    issued_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    issued_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    delivered_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)          # 워커가 보고한 결과 (JSON 또는 텍스트)
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_wcmd_worker_status", "worker_id", "status"),
        Index("idx_wcmd_issued", "issued_at"),
    )


class WorkerError(Base):
    """워커가 서버로 리포트한 에러/진단 로그.

    원격 디버깅 목적 — 워커 PC 에 직접 접속 안 해도 어드민 UI 에서 확인 가능.
    rolling window: 같은 (worker_id, kind, message) 10분 내 중복은 drop (서버 측).
    retention: 7일 (별도 cleanup job 또는 수동 vacuum).
    """
    __tablename__ = "worker_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    kind = Column(String(32), nullable=False)           # heartbeat_fail, task_fail, diagnostic, update_fail, other
    message = Column(Text, nullable=False)              # 한 줄 요약
    traceback = Column(Text, nullable=True)             # full traceback (있으면)
    context = Column(Text, nullable=True)               # JSON — task_id, url, etc
    screenshot_url = Column(Text, nullable=True)        # 디스크 상대경로 e.g. 2026-04-25/<worker>-<ts>-<rand>.png
    occurred_at = Column(DateTime, nullable=False)      # 워커가 기록한 시각
    received_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_werr_worker_time", "worker_id", "received_at"),
        Index("idx_werr_kind_time", "kind", "received_at"),
    )


class CommentSnapshot(Base):
    """Periodic snapshot of one of our comments — used to track ranking / hold / ghost over time.

    Background scheduler (or worker like_boost task) opens the video page from a
    different (rotation) viewer account, finds our comment by youtube_comment_id,
    and records:
      - rank: position in default 'top comments' (None if not in first N)
      - like_count: how many likes the comment has accumulated
      - reply_count: how many replies under it
      - visible_to_third_party: True if seen from a different (clean) profile
      - is_held: True if comment shows 'pending review' badge
    """
    __tablename__ = "comment_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    video_id = Column(String, ForeignKey("videos.id"), nullable=False)
    youtube_comment_id = Column(String, nullable=False)  # Ugxxx
    posted_at = Column(DateTime, nullable=True)          # original post time
    captured_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    rank = Column(Integer, nullable=True)                # 1=top, None=not in top N scanned
    rank_scope = Column(Integer, default=20)             # how many top threads we scanned
    like_count = Column(Integer, default=0)
    reply_count = Column(Integer, default=0)

    visible_to_third_party = Column(Boolean, default=True)
    is_held = Column(Boolean, default=False)             # 'held for review' badge present
    is_deleted = Column(Boolean, default=False)          # comment vanished entirely

    captured_by_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # 누가 봤는지

    __table_args__ = (
        Index("idx_snap_yt_id", "youtube_comment_id", "captured_at"),
        Index("idx_snap_video_time", "video_id", "captured_at"),
        Index("idx_snap_account", "account_id", "captured_at"),
    )


class AuditLog(Base):
    """관리자 액션 감사 로그 — 누가/언제/무엇을 기록.

    SQLAlchemy Declarative 에서 'metadata' 는 예약어라 'metadata_json' 사용.
    민감 정보는 미들웨어에서 필터 후 저장.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(64), nullable=False)         # deploy, pause, campaign_create 등
    target_type = Column(String(32), nullable=True)     # campaign, account, worker, preset
    target_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)         # JSON
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "timestamp"),
        Index("idx_audit_action_time", "action", "timestamp"),
    )


# ─────────────────────────────────────────────────────────────────
# Phase 1 — 신규 테이블 (Smart Pickup 명세 채택)
# ─────────────────────────────────────────────────────────────────


class TargetCollectionConfig(Base):
    """Brand(=Target) 별 수집·분류 정책. 운영 디폴트값 박혀있음."""
    __tablename__ = "target_collection_config"

    target_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True)
    # L1 풀
    l1_threshold_score = Column(Float, default=70.0, nullable=False)
    l1_max_pool_size = Column(Integer, default=1000, nullable=False)
    # L2 신규
    l2_max_age_hours = Column(Integer, default=24, nullable=False)
    l2_min_channel_subscribers = Column(Integer, default=10000, nullable=False)
    # L3 트렌딩
    l3_views_per_hour_threshold = Column(Integer, default=1000, nullable=False)
    l3_views_24h_threshold = Column(Integer, default=10000, nullable=False)
    # 임베딩
    embedding_reference_text = Column(Text)
    embedding_threshold = Column(Float, default=0.65, nullable=False)
    # 룰 필터
    hard_block_min_video_seconds = Column(Integer, default=30, nullable=False)
    exclude_kids_category = Column(Boolean, default=True, nullable=False)
    exclude_live_streaming = Column(Boolean, default=True, nullable=False)
    # 점수 가중치 JSON
    score_weights = Column(Text)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)


class YoutubeVideoGlobalState(Base):
    """같은 YouTube 영상이 여러 타겟에서 동시 작전 시 충돌 방지용 글로벌 상태."""
    __tablename__ = "youtube_video_global_state"

    youtube_video_id = Column(String(20), primary_key=True)
    total_actions_24h = Column(Integer, default=0, nullable=False)
    total_actions_7d = Column(Integer, default=0, nullable=False)
    active_target_count = Column(SmallInteger, default=0, nullable=False)
    active_scenario_count = Column(SmallInteger, default=0, nullable=False)
    last_action_at = Column(DateTime)
    last_main_comment_at = Column(DateTime)
    recent_action_log = Column(Text)  # JSON array
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        Index("idx_global_state_actions_24h", "total_actions_24h"),
    )


class VideoKeywordMatch(Base):
    """영상이 어떤 키워드의 검색 결과 상위에 등장했는지 추적 (검색 노출도 점수용)."""
    __tablename__ = "video_keyword_matches"

    match_id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False)
    search_rank = Column(SmallInteger)
    matched_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("video_id", "keyword_id", name="uq_video_keyword"),
        Index("idx_match_video", "video_id"),
    )


class ChannelBlacklist(Base):
    """채널 단위 차단. target_id NULL = 전 시스템 글로벌 차단."""
    __tablename__ = "channel_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(String(50), nullable=False)
    target_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"))  # NULL = global
    reason = Column(String(100))
    added_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    __table_args__ = (
        UniqueConstraint("channel_id", "target_id", name="uq_channel_target"),
        Index("idx_channel_blacklist_global", "channel_id"),
    )


class TargetCategoryFitness(Base):
    """Phase 2: 타겟별 LLM 카테고리의 적합도 (0~1). 어드민에서 편집."""
    __tablename__ = "target_category_fitness"

    target_id = Column(Integer, ForeignKey("brands.id", ondelete="CASCADE"), primary_key=True)
    category = Column(String(50), primary_key=True)
    fitness = Column(Float, default=0.5, nullable=False)


class VideoCollectionLog(Base):
    """수집 작업 추적 (운영 디버그·모니터링)."""
    __tablename__ = "video_collection_log"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    target_id = Column(Integer, nullable=False)
    poll_type = Column(String(20))
    keywords_processed = Column(Integer, default=0, nullable=False)
    api_calls_made = Column(Integer, default=0, nullable=False)
    videos_found = Column(Integer, default=0, nullable=False)
    videos_new = Column(Integer, default=0, nullable=False)
    videos_updated = Column(Integer, default=0, nullable=False)
    videos_blocked = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(20))
    error_message = Column(Text)

    __table_args__ = (
        Index("idx_collection_log_target_started", "target_id", "started_at"),
    )


class YoutubeQuotaLog(Base):
    """API 키별 일일 quota 사용량. 5분 폴링 도입 시 필수."""
    __tablename__ = "youtube_quota_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_index = Column(Integer, nullable=False)
    day = Column(Date, nullable=False)
    quota_used = Column(Integer, default=0, nullable=False)
    last_request_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("api_key_index", "day", name="uq_quota_per_day"),
        Index("idx_quota_day", "day"),
    )
