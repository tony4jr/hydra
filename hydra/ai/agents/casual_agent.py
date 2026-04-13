"""Non-promotional comment generation agent (Haiku).

Generates generic reactions that don't mention any brand.
Lower cost, can be cached and reused.
"""

from hydra.ai.base import get_model, log
from hydra.ai.harness import call_claude, load_prompt


def generate_non_promo_comment(persona: dict, video_title: str) -> str:
    """Generate a non-promotional comment.

    These are generic reactions that don't mention any brand.
    """
    system = load_prompt(
        "casual_system",
        speech_style=persona.get("speech_style", "편한 존댓말"),
        emoji_frequency=persona.get("emoji_frequency", "medium"),
        comment_length=persona.get("comment_length", "medium"),
    )

    comment = call_claude(
        model=get_model("casual"),
        system=system,
        user_message=f"영상: {video_title}",
        max_tokens=150,
        max_retries=2,
    )
    log.info(f"Generated casual comment: {comment[:50]}...")
    return comment
