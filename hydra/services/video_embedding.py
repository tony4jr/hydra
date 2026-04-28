"""Phase 1 — 영상 관련도 분류 (Stage A).

Claude Haiku 4.5 사용 — 별도 임베딩 모델 안 씀 (OpenAI 의존성 X).

영상 제목+설명 vs 타겟 reference text → 0~1 관련도 점수.
embedding_threshold (default 0.65) 미만이면 'blacklisted' (low_relevance).

비용: Haiku 4.5 입력 ~300 + 출력 ~20 = 영상당 약 $0.0003.
일 1000 영상 처리 = 약 $0.30/일.

함수명은 historical (embedding) 유지 — 기존 호출처 호환.
"""
from __future__ import annotations

import json
import logging
import re
from sqlalchemy.orm import Session

from hydra.db.models import Video, TargetCollectionConfig

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 YouTube 영상 분류 전문가입니다.
주어진 영상 제목+설명이 타겟 시장(reference)과 얼마나 관련 있는지 0~1 점수로 평가하세요.

평가 기준:
- 1.0: 완벽 일치 (예: 탈모 시장 reference 와 "탈모 영양제 후기" 영상)
- 0.7~0.9: 강한 관련 (예: "두피 케어 방법")
- 0.4~0.6: 약한 관련 (예: "건강기능식품 일반")
- 0.0~0.3: 무관 (예: "강아지 산책")

반드시 JSON 으로만 응답:
{"score": 0.0~1.0, "reason": "한 줄 설명"}
"""


def _build_user_msg(reference_text: str, title: str, description: str) -> str:
    desc = (description or "")[:300]
    return f"""[타겟 reference]
{reference_text}

[영상 제목]
{title or "(제목 없음)"}

[영상 설명]
{desc or "(설명 없음)"}
"""


def _extract_score(text: str) -> float | None:
    """Claude 응답에서 score 추출. JSON 파싱 실패 시 정규식 fallback."""
    # JSON 블록 찾기
    json_match = re.search(r'\{[^{}]*"score"[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            score = float(data.get("score", -1))
            if 0.0 <= score <= 1.0:
                return score
        except (ValueError, json.JSONDecodeError):
            pass

    # Fallback: 숫자만
    num_match = re.search(r'\b(0?\.\d+|1\.0+|0+|1)\b', text)
    if num_match:
        try:
            score = float(num_match.group())
            if 0.0 <= score <= 1.0:
                return score
        except ValueError:
            pass

    return None


def compute_relevance_score(
    db: Session,
    video: Video,
    target_id: int,
) -> float | None:
    """영상의 타겟 관련도 점수 (0~1). 실패 시 None.

    Claude Haiku 호출. 영상당 약 $0.0003.
    """
    cfg = db.get(TargetCollectionConfig, target_id)
    if cfg is None or not cfg.embedding_reference_text:
        # reference text 없으면 임의 통과 (운영자가 아직 설정 안 함)
        return None

    title = video.title or ""
    desc = (video.description or "")[:300]
    if not title and not desc:
        return None

    try:
        from hydra.ai.harness import call_claude
        from hydra.ai.base import MODEL_HAIKU

        user_msg = _build_user_msg(cfg.embedding_reference_text, title, desc)
        text = call_claude(
            model=MODEL_HAIKU,
            system=SYSTEM_PROMPT,
            user_message=user_msg,
            max_tokens=100,
            max_retries=2,
        )
        return _extract_score(text)
    except Exception as e:
        log.error(f"Haiku relevance check failed: {e}")
        return None


def classify_by_embedding(
    db: Session,
    video: Video,
    target_id: int,
) -> tuple[bool, str | None]:
    """관련도 점수 계산 + threshold 검사.

    Returns:
        (passed, blacklist_reason).
        passed=True 면 video.embedding_score 채워짐 (값 이름은 historical 임).
        passed=False 면 video.state='blacklisted' + reason.
    """
    score = compute_relevance_score(db, video, target_id)
    if score is None:
        # 분류 실패 (키 없거나 reference 없거나 API 에러) — 통과
        log.debug(f"relevance skip for {video.id} (no score)")
        return True, None

    video.embedding_score = score

    cfg = db.get(TargetCollectionConfig, target_id)
    threshold = (cfg.embedding_threshold if cfg else 0.65) or 0.65

    if score < threshold:
        return False, f"low_relevance:{score:.2f}"

    return True, None


def get_target_reference_embedding(db: Session, target_id: int):
    """Historical: OpenAI 임베딩 시절 reference 벡터. 이제 Claude 호출이라 N/A."""
    cfg = db.get(TargetCollectionConfig, target_id)
    return cfg.embedding_reference_text if cfg else None


def reset_reference_cache(target_id: int | None = None) -> None:
    """Historical: 캐시 무효화. Claude Haiku 는 매번 직접 호출하므로 no-op."""
    pass
