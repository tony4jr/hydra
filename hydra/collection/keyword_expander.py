"""Keyword auto-expansion using Claude.

Spec 4.2: operator enters "탈모 영양제" → Claude generates related keywords.
Saved as source='auto_expanded', operator reviews in UI.
"""

import json

import anthropic
from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.db.models import Keyword, Brand

log = get_logger("keyword_expander")


def expand_keywords(db: Session, keyword: Keyword, max_count: int = 15) -> list[Keyword]:
    """Generate related keywords using Claude.

    Returns list of newly created Keyword records.
    """
    brand = db.query(Brand).get(keyword.brand_id) if keyword.brand_id else None
    brand_context = ""
    if brand:
        brand_context = f"\n브랜드: {brand.name}\n카테고리: {brand.product_category or ''}"

    client = anthropic.Anthropic(api_key=settings.claude_api_key)

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""한국 YouTube에서 검색할 관련 키워드를 {max_count}개 생성해주세요.

원본 키워드: "{keyword.text}"{brand_context}

규칙:
- 한국어로 작성
- 실제 사람들이 YouTube에서 검색할 법한 자연스러운 표현
- 너무 광범위하지 않게 (관련성 유지)
- JSON 배열로만 출력: ["키워드1", "키워드2", ...]"""
        }],
    )

    text = resp.content[0].text.strip()
    start = text.index("[")
    end = text.rindex("]") + 1
    suggestions = json.loads(text[start:end])

    created = []
    for kw_text in suggestions:
        kw_text = kw_text.strip()
        if not kw_text:
            continue

        # Skip if already exists
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
        )
        db.add(new_kw)
        created.append(new_kw)

    db.commit()
    log.info(f"Expanded '{keyword.text}' → {len(created)} new keywords")
    return created
