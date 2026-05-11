"""Worker ↔ Server protocol contracts.

Server is the control plane (source of truth for accounts, tasks, dispatch).
Workers are stateless executors that receive self-contained envelopes.

Models here are imported from BOTH server and worker code — they ARE the
contract. Any breaking change requires bumping `TaskEnvelope.schema_version`
and providing transitional support.
"""
from hydra.protocol.task_envelope import (
    AccountSnapshot,
    TaskEnvelope,
    WorkerConfig,
    redact_for_logging,
)

__all__ = [
    "AccountSnapshot",
    "TaskEnvelope",
    "WorkerConfig",
    "redact_for_logging",
]
