"""Shared Claude API client and model constants."""

import anthropic

from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("ai.base")

# Model assignments per agent type
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

AGENT_MODELS = {
    "comment": MODEL_HAIKU,
    "reply": MODEL_HAIKU,
    "persona": MODEL_SONNET,
    "keyword": MODEL_SONNET,
    "casual": MODEL_HAIKU,
    "slot": MODEL_HAIKU,
    # Phase 4 — 운영 보조 AI
    "error_summary": MODEL_HAIKU,       # 단순 요약, Haiku 충분
    "screen_classifier": MODEL_SONNET,  # vision 분류 (P4 후속, 데이터 모인 후)
}

_client: anthropic.Anthropic | None = None


def _load_claude_key() -> str:
    """DB system_config (UI 저장) 우선, .env (settings) fallback."""
    try:
        from hydra.db.session import SessionLocal
        from hydra.db.models import SystemConfig
        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(SystemConfig.key == "claude_api_key").first()
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception:
        pass
    return settings.claude_api_key


def get_client() -> anthropic.Anthropic:
    """Get or create a shared Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=_load_claude_key())
    return _client


def get_model(agent_name: str) -> str:
    """Get the model for a given agent. Falls back to Sonnet."""
    return AGENT_MODELS.get(agent_name, MODEL_SONNET)
