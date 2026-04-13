"""DEPRECATED — Moved to hydra.ai.agents.comment_agent and hydra.ai.agents.casual_agent.

This module re-exports for backward compatibility.
"""

# Re-exports
from hydra.ai.agents.comment_agent import generate_comment  # noqa: F401
from hydra.ai.agents.casual_agent import generate_non_promo_comment  # noqa: F401
from hydra.ai.evaluator import validate_comment  # noqa: F401
from hydra.ai.agents.comment_agent import ROLE_PROMPTS  # noqa: F401

from sqlalchemy.orm import Session
from hydra.db.models import ActionLog


def check_duplicate(db: Session, comment: str, account_id: int) -> bool:
    """Check if this exact comment was already posted by this account."""
    existing = (
        db.query(ActionLog)
        .filter(
            ActionLog.account_id == account_id,
            ActionLog.content == comment,
        )
        .first()
    )
    return existing is not None
