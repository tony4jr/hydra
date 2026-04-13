"""Post-generation validation for comments."""

import re


def validate_comment(
    comment: str,
    banned_keywords: list[str],
    brand_name: str,
    mention_rules: dict,
) -> list[str]:
    """Validate a generated comment. Returns list of issues (empty = OK)."""
    issues = []

    for kw in banned_keywords:
        if kw in comment:
            issues.append(f"금지 키워드 포함: '{kw}'")

    if not mention_rules.get("brand_direct") and brand_name in comment:
        issues.append(f"브랜드명 직접 언급 불가: '{brand_name}'")

    if len(comment) > 500:
        issues.append("댓글 500자 초과")
    if len(comment) < 2:
        issues.append("댓글 너무 짧음")

    ad_patterns = [r"구매.*링크", r"할인.*코드", r"지금.*구매", r"클릭.*여기"]
    for pattern in ad_patterns:
        if re.search(pattern, comment):
            issues.append(f"광고 패턴 감지: {pattern}")

    return issues
