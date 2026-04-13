"""Reply generation agent (Sonnet).

Generates contextual replies to existing YouTube comments.
Reuses comment_agent's infrastructure but with reply-specific logic.
"""

from hydra.ai.agents.comment_agent import generate_comment
from hydra.core.enums import AccountRole
from hydra.db.models import Brand, Video


def generate_reply(
    persona: dict,
    role: AccountRole,
    brand: Brand,
    video: Video,
    parent_comment: str,
    context: str = "",
    max_retries: int = 3,
) -> str:
    """Generate a reply to an existing comment.

    Delegates to comment_agent with is_reply=True.
    """
    return generate_comment(
        persona=persona,
        role=role,
        brand=brand,
        video=video,
        context=context,
        is_reply=True,
        parent_comment=parent_comment,
        max_retries=max_retries,
    )
