"""AI harness — retry logic, structured output extraction, rate limit handling."""

import json
import time
from pathlib import Path
from typing import Any

import anthropic

from hydra.ai.base import get_client, log

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str, **kwargs: Any) -> str:
    """Load a prompt template from prompts/ dir and format with kwargs."""
    path = PROMPTS_DIR / f"{name}.txt"
    template = path.read_text(encoding="utf-8")
    if kwargs:
        template = template.format(**kwargs)
    return template


def _log_token_usage(
    *, agent_name: str, model: str, usage: Any,
    task_id: int | None, account_id: int | None,
) -> None:
    """ai_token_usage 적재. 실패해도 작업은 진행 (silent log)."""
    try:
        from hydra.db.session import SessionLocal
        from hydra.db.models import AITokenUsage
        db = SessionLocal()
        try:
            row = AITokenUsage(
                agent_name=agent_name,
                model=model,
                input_tokens=getattr(usage, "input_tokens", 0) or 0,
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                task_id=task_id,
                account_id=account_id,
            )
            db.add(row)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        log.warning(f"ai_token_usage log failed: {type(e).__name__}: {e}")


def call_claude(
    *,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 300,
    max_retries: int = 3,
    validator: Any | None = None,
    retry_hint_fn: Any | None = None,
    agent_name: str = "unknown",
    task_id: int | None = None,
    account_id: int | None = None,
) -> str:
    """Call Claude with retry, rate-limit handling, and optional validation.

    Args:
        model: Model ID to use.
        system: System prompt.
        user_message: User message content.
        max_tokens: Max output tokens.
        max_retries: Number of attempts.
        validator: Optional callable(text) -> list[str]. Returns issues list (empty=OK).
        retry_hint_fn: Optional callable(issues) -> str. Generates hint appended on retry.

    Returns:
        Generated text (stripped).
    """
    client = get_client()
    current_msg = user_message

    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": current_msg}],
            )
            _log_token_usage(
                agent_name=agent_name, model=model, usage=resp.usage,
                task_id=task_id, account_id=account_id,
            )
            text = resp.content[0].text.strip()

            # Strip wrapping quotes
            text = text.strip('"').strip("'")

            if validator:
                issues = validator(text)
                if issues:
                    log.warning(f"Validation failed (attempt {attempt + 1}): {issues}")
                    if retry_hint_fn:
                        current_msg += "\n\n" + retry_hint_fn(issues)
                    continue
            return text

        except anthropic.RateLimitError:
            log.warning("Claude rate limit, waiting 60s")
            time.sleep(60)
        except Exception as e:
            log.error(f"Claude API error: {e}")
            if attempt == max_retries - 1:
                raise

    raise RuntimeError(f"Failed after {max_retries} attempts")


def extract_json(text: str, container: str = "{") -> Any:
    """Extract JSON object or array from text that may contain surrounding prose.

    Args:
        container: '{' for object, '[' for array.
    """
    close = "}" if container == "{" else "]"
    start = text.index(container)
    end = text.rindex(close) + 1
    return json.loads(text[start:end])
