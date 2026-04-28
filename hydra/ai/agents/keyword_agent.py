"""Keyword expansion agent (Sonnet).

Generates related YouTube search keywords from a seed keyword.
"""

from sqlalchemy.orm import Session

from hydra.ai.base import get_model, log
from hydra.ai.harness import call_claude, load_prompt, extract_json
from hydra.db.models import Keyword, Brand


def expand_keywords(db: Session, keyword: Keyword, max_count: int = 15) -> list[Keyword]:
    """Generate related keywords using Claude.

    Returns list of newly created Keyword records.
    """
    brand = db.query(Brand).get(keyword.brand_id) if keyword.brand_id else None
    brand_context = ""
    if brand:
        brand_context = f"\n브랜드: {brand.name}\n카테고리: {brand.product_category or ''}"

    user_msg = load_prompt(
        "keyword_user",
        max_count=max_count,
        keyword_text=keyword.text,
        brand_context=brand_context,
    )

    text = call_claude(
        model=get_model("keyword"),
        system="",
        user_message=user_msg,
        max_tokens=500,
        max_retries=2,
    )

    suggestions = extract_json(text, "[")

    created = []
    for kw_text in suggestions:
        kw_text = kw_text.strip()
        if not kw_text:
            continue

        existing = db.query(Keyword).filter(
            Keyword.text == kw_text,
            Keyword.brand_id == keyword.brand_id,
        ).first()
        if existing:
            continue

        new_kw = Keyword(
            text=kw_text,
            brand_id=keyword.brand_id,
            source="auto_expanded",
            status="active",
            priority=keyword.priority - 1 if keyword.priority > 1 else 1,
            parent_keyword_id=keyword.id,
            is_variant=True,
        )
        db.add(new_kw)
        created.append(new_kw)

    db.commit()
    log.info(f"Expanded '{keyword.text}' → {len(created)} new keywords")
    return created
