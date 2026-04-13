"""Shared Claude API client and model constants."""

import anthropic

from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("ai.base")

# Model assignments per agent type
MODEL_SONNET = "claude-sonnet-4-20250514"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

AGENT_MODELS = {
    "comment": MODEL_SONNET,
    "reply": MODEL_SONNET,
    "persona": MODEL_SONNET,
    "keyword": MODEL_SONNET,
    "casual": MODEL_HAIKU,
}

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """Get or create a shared Anthropic client."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.claude_api_key)
    return _client


def get_model(agent_name: str) -> str:
    """Get the model for a given agent. Falls back to Sonnet."""
    return AGENT_MODELS.get(agent_name, MODEL_SONNET)
