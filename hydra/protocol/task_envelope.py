"""TaskEnvelope: server → worker dispatch contract.

A worker receives an envelope and must be able to execute the task using ONLY
the envelope (no local DB lookup for accounts/workers). The server is the
source of truth.

Schema versioning:
- `TaskEnvelope.schema_version` follows semver-ish "MAJOR.MINOR".
- MINOR bumps add optional fields (backwards compatible).
- MAJOR bumps may change/remove fields; servers should support old workers
  via transitional response shape until they drop out of the fleet.

Secrets:
- AccountSnapshot.encrypted_password and encrypted_totp_secret are encrypted
  at rest but still sensitive in flight. Use `redact_for_logging()` before
  logging/error-reporting any envelope.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

# Fields that must NEVER appear in logs / error reports / screenshots context.
SECRET_FIELDS = frozenset({
    "encrypted_password",
    "password",
    "encrypted_totp_secret",
    "totp_secret",
    "cookies",
    "adspower_api_key",
    "worker_token",
})


class AccountSnapshot(BaseModel):
    """Everything a worker needs to operate one account, without local lookup."""

    model_config = ConfigDict(extra="ignore", frozen=False)

    id: int
    gmail: str
    encrypted_password: str = Field(..., description="Encrypted at rest. Sensitive.")
    recovery_email: Optional[str] = None
    adspower_profile_id: Optional[str] = None
    persona: Optional[str] = Field(None, description="JSON string. Worker parses for behavior tuning.")
    encrypted_totp_secret: Optional[str] = None
    status: str = "active"
    ipp_flagged: bool = False
    youtube_channel_id: Optional[str] = None


class WorkerConfig(BaseModel):
    """Server-issued knobs the worker should respect for this dispatch.

    Worker may also have local env-based defaults; these override.
    """

    model_config = ConfigDict(extra="ignore", frozen=False)

    adb_device_id: Optional[str] = Field(
        None, description="If set, worker uses this for IP rotation. Else falls back to local env."
    )
    ip_cooldown_minutes: int = Field(
        30, description="IpLog cross-account cooldown window."
    )
    max_session_minutes: int = 45
    max_tasks_per_session: int = 8


class TaskEnvelope(BaseModel):
    """Self-contained task dispatch envelope.

    Workers MUST be able to execute the task with only this envelope —
    no DB queries against local Account/Worker tables.
    """

    model_config = ConfigDict(extra="ignore", frozen=False)

    schema_version: str = SCHEMA_VERSION
    task_id: int
    task_type: str
    priority: str = "normal"
    deadline: Optional[datetime] = Field(
        None, description="If set, worker should not start after this time."
    )
    payload: Optional[str] = Field(None, description="JSON string. Task-type specific.")
    account: AccountSnapshot
    worker_config: WorkerConfig = Field(default_factory=WorkerConfig)
    # Instructions reserved for future explicit action lists. PR-A keeps this
    # empty; executors continue to derive actions from payload + task_type.
    instructions: list[dict[str, Any]] = Field(default_factory=list)


def redact_for_logging(data: Any) -> Any:
    """Return a copy of `data` with secret fields masked.

    Accepts: dict, list, BaseModel, scalar. Recurses into nested structures.
    """
    if isinstance(data, BaseModel):
        data = data.model_dump()
    if isinstance(data, dict):
        return {
            k: ("***REDACTED***" if k in SECRET_FIELDS else redact_for_logging(v))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [redact_for_logging(item) for item in data]
    return data
