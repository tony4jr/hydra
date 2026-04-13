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


def call_claude(
    *,
    model: str,
    system: str,
    user_message: str,
    max_tokens: int = 300,
    max_retries: int = 3,
    validator: Any | None = None,
    retry_hint_fn: Any | None = None,
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
