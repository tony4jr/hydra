"""All enums and constants from the operations spec."""

from enum import StrEnum


# --- Account ---

class AccountStatus(StrEnum):
    REGISTERED = "registered"
    PROFILE_SET = "profile_set"
    WARMUP = "warmup"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    CAPTCHA_STUCK = "captcha_stuck"
    LOGIN_FAILED = "login_failed"
    CHECKPOINT = "checkpoint"
    IP_BLOCKED = "ip_blocked"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class WarmupGroup(StrEnum):
    A = "A"   # 1~2일
    B = "B"   # 3일
    C = "C"   # 7일
    D = "D"   # 14일
    E = "E"   # 21일


WARMUP_DAYS = {"A": 2, "B": 3, "C": 7, "D": 14, "E": 21}


# --- Roles ---

class AccountRole(StrEnum):
    SEED = "seed"
    ASKER = "asker"
    WITNESS = "witness"
    AGREE = "agree"
    CURIOUS = "curious"
    INFO = "info"
    FAN = "fan"
    QA = "qa"


# --- Scenarios ---

class Scenario(StrEnum):
    A = "A"   # 씨앗 심기
    B = "B"   # 자연스러운 질문 유도
    C = "C"   # 동조 여론 형성
    D = "D"   # 비포애프터 경험담
    E = "E"   # 슥 지나가기
    F = "F"   # 정보형 교육
    G = "G"   # 남의 댓글 올라타기
    H = "H"   # 반박 → 중재
    I = "I"   # 간접 경험 (선물·추천)
    J = "J"   # 숏폼 전용


# --- Campaign ---

class CampaignStatus(StrEnum):
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(StrEnum):
    COMMENT = "comment"
    REPLY = "reply"
    LIKE = "like"
    LIKE_BOOST = "like_boost"


# --- Video ---

class VideoStatus(StrEnum):
    AVAILABLE = "available"
    DELETED = "deleted"
    COMMENTS_DISABLED = "comments_disabled"
    AGE_RESTRICTED = "age_restricted"


class VideoPriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# --- Like Boost ---

class LikeBoostPreset(StrEnum):
    CONSERVATIVE = "conservative"
    NORMAL = "normal"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


# --- Ghost ---

class GhostCheckStatus(StrEnum):
    PENDING = "pending"
    VISIBLE = "visible"
    SUSPICIOUS = "suspicious"
    GHOST = "ghost"
    UNCHECKED = "unchecked"


# --- Action Log ---

class ActionType(StrEnum):
    VIEW = "view"
    COMMENT = "comment"
    REPLY = "reply"
    LIKE_VIDEO = "like_video"
    LIKE_COMMENT = "like_comment"
    SUBSCRIBE = "subscribe"
    SEARCH = "search"
    SCROLL = "scroll"
    SHORTS_SWIPE = "shorts_swipe"


# --- Error ---

class ErrorLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorSource(StrEnum):
    CHROME = "chrome"
    YOUTUBE = "youtube"
    CLAUDE = "claude"
    IP = "ip"
    SYSTEM = "system"


# --- Keyword ---

class KeywordSource(StrEnum):
    MANUAL = "manual"
    AUTO_EXPANDED = "auto_expanded"
    TRENDING = "trending"


class KeywordStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    EXCLUDED = "excluded"


# --- Worker ---

class WorkerStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    PAUSED = "paused"


# --- Task ---

class TaskStatus(StrEnum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskType(StrEnum):
    COMMENT = "comment"
    REPLY = "reply"
    LIKE = "like"
    LIKE_BOOST = "like_boost"
    SUBSCRIBE = "subscribe"
    WARMUP = "warmup"
    GHOST_CHECK = "ghost_check"
    PROFILE_SETUP = "profile_setup"


class TaskPriority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# --- Campaign v2 ---

class CampaignType(StrEnum):
    SCENARIO = "scenario"
    DIRECT = "direct"


class CommentMode(StrEnum):
    AI_AUTO = "ai_auto"
    AI_APPROVE = "ai_approve"
    MANUAL = "manual"
