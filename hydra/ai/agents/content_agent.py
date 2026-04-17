"""content_agent — 프리셋 기반 대화 흐름 생성.

기존 comment/reply/casual 에이전트를 통합하여,
프리셋의 전체 스텝을 하나의 대화 흐름으로 생성한다.
"""
import json
from hydra.ai.base import get_client, get_model
from hydra.ai.harness import call_claude, load_prompt

# 프로모 스텝은 Sonnet, 동조/캐주얼은 Haiku
PROMO_ROLES = {"seed", "info", "witness", "qa"}
CASUAL_ROLES = {"agree", "fan", "curious", "asker"}

# 페르소나 말투 가이드
PERSONA_SPEECH = {
    "대학생": "축약어 많이 (ㅋㅋ, ㄹㅇ, ;;), 반말 위주, 전문 용어 안 씀, 친구한테 말하듯이",
    "회사원": "반말+존댓말 혼용, ㅋㅋ 적당히, 자기 경험 위주",
    "주부": "존댓말 위주, 공감 표현 많이 (맞아요, 저도요), ㅠㅠ .. 자주 사용",
    "전문직": "정중한 존댓말, 전문 용어 자연스럽게, 근거 기반",
    "자영업": "실용적 톤, 직접 써본 후기 위주",
    "프리랜서": "캐주얼, 자기 경험 기반",
}


def _select_model(role: str) -> str:
    """역할에 따라 모델 선택."""
    if role in PROMO_ROLES:
        return get_model("comment")  # Sonnet
    return get_model("casual")  # Haiku


def _fetch_transcript(video_id: str) -> str:
    """YouTube 영상 자막/스크립트 가져오기."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
        # 전체 텍스트 합치기 (최대 2000자)
        full_text = " ".join([t["text"] for t in transcript_list])
        return full_text[:2000]
    except Exception:
        return ""


def generate_conversation(
    brand: dict,
    preset_steps: list[dict],
    video: dict,
    personas: list[dict] | None = None,
    previous_results: list[str] | None = None,
) -> list[dict]:
    """프리셋 스텝 전체에 대한 대화 흐름 생성.

    Args:
        brand: {"name": str, "product": str, "core_message": str, "keywords": list, "tone_guide": str}
        preset_steps: [{"step_number": int, "role": str, "type": str, "tone": str, "target": str}]
        video: {"title": str, "description": str, "url": str}
        personas: Optional list of persona dicts for each step
        previous_results: 이전에 생성된 댓글들 (중복 방지용)

    Returns:
        [{"step_number": int, "role": str, "text": str}]
    """
    # 영상 스크립트 가져오기
    video_id = video.get("url", "").split("v=")[-1].split("&")[0] if video.get("url") else ""
    transcript = _fetch_transcript(video_id) if video_id else ""

    results = []
    conversation_context = []  # 이전 스텝의 결과를 맥락으로 전달

    for i, step in enumerate(preset_steps):
        role = step.get("role", "seed")
        tone = step.get("tone", "자연스러운")
        target = step.get("target", "main")
        step_type = step.get("type", "comment")

        model = _select_model(role)

        # 페르소나 가져오기
        persona = personas[i] if personas and i < len(personas) else None

        # 시스템 프롬프트 구성
        system_prompt = _build_system_prompt(brand, role, tone, persona)

        # 유저 메시지 구성
        user_message = _build_user_message(
            video=video,
            step=step,
            conversation_context=conversation_context,
            persona=persona,
            previous_results=previous_results,
            transcript=transcript,
        )

        # 댓글 생성
        text = call_claude(
            model=model,
            system=system_prompt,
            user_message=user_message,
            max_tokens=300 if role in PROMO_ROLES else 150,
            validator=lambda t: _validate_comment(t, brand),
        )

        result = {
            "step_number": step["step_number"],
            "role": role,
            "type": step_type,
            "text": text,
        }
        results.append(result)
        conversation_context.append(result)

    return results

def _build_system_prompt(brand: dict, role: str, tone: str, persona: dict | None = None) -> str:
    """역할과 톤에 맞는 시스템 프롬프트 생성."""
    brand_name = brand.get("name", "")
    product = brand.get("product", "")
    core_message = brand.get("core_message", "")
    tone_guide = brand.get("tone_guide", "자연스럽고 진솔한 말투")

    base = f"""당신은 YouTube 영상에 댓글을 다는 일반 사용자입니다.
절대 광고처럼 보여서는 안 됩니다. 자연스러운 일반인의 말투로 작성하세요.

역할: {role}
톤: {tone}
말투 가이드: {tone_guide}

브랜드 정보 (자연스럽게 녹여야 함, 직접 광고 금지):
- 브랜드: {brand_name}
- 제품: {product}
- 핵심 메시지: {core_message}

규칙:
- 한국어로 작성
- 이모지 자제 (가끔 1개 정도 OK)
- 광고 문구 절대 금지 ("최고의", "강력 추천", "꼭 써보세요" 등)
- 자연스러운 줄임말, 구어체 사용
- 너무 길지 않게 (1~3문장)
- 같은 표현 반복 금지"""

    # 페르소나 말투 강화
    if persona:
        occupation = persona.get("occupation", "")
        age = persona.get("age", "")
        gender = persona.get("gender", "")
        speech = PERSONA_SPEECH.get(occupation, "자연스러운 구어체, 평범한 말투")
        base += f"""

페르소나:
- {age}대 {gender} {occupation}
- 말투: {speech}
- 이 사람이 실제로 댓글을 달듯이 작성하세요"""

    return base

def _build_user_message(
    video: dict,
    step: dict,
    conversation_context: list[dict],
    persona: dict | None,
    previous_results: list[str] | None,
    transcript: str = "",
) -> str:
    """유저 메시지 구성."""
    parts = []

    # 영상 정보
    parts.append(f"영상 제목: {video.get('title', '')}")
    if video.get("description"):
        parts.append(f"영상 설명: {video['description'][:200]}")

    # 영상 스크립트 (자막)
    if transcript:
        parts.append(f"\n영상 스크립트 (자막):\n{transcript[:1000]}")

    # 페르소나
    if persona:
        parts.append(f"\n당신의 캐릭터: {persona.get('age', '')}대 {persona.get('gender', '')} {persona.get('occupation', '')}")

    # 이전 대화 맥락
    if conversation_context:
        parts.append("\n이전 대화:")
        for prev in conversation_context:
            parts.append(f"  [{prev['role']}] {prev['text']}")

    # 현재 스텝 지시
    step_type = step.get("type", "comment")
    target = step.get("target", "main")
    tone = step.get("tone", "")

    if step_type == "comment":
        parts.append(f"\n이 영상에 '{tone}' 톤으로 댓글을 작성하세요.")
    elif step_type == "reply":
        if target.startswith("step_"):
            step_num = int(target.split("_")[1])
            ref = next((c for c in conversation_context if c["step_number"] == step_num), None)
            if ref:
                parts.append(f"\n위 [{ref['role']}]의 댓글에 '{tone}' 톤으로 대댓글을 작성하세요.")
        else:
            parts.append(f"\n'{tone}' 톤으로 대댓글을 작성하세요.")

    # 중복 방지
    if previous_results:
        parts.append(f"\n다음과 다른 새로운 표현을 사용하세요: {', '.join(previous_results[:5])}")

    parts.append("\n댓글 텍스트만 출력하세요. 따옴표나 설명 없이.")

    return "\n".join(parts)

def _validate_comment(text: str, brand: dict) -> list[str]:
    """댓글 검증 — 금지어, 광고성 체크.

    Returns:
        빈 리스트이면 통과, 문제가 있으면 사유 문자열 리스트.
    """
    issues = []

    if not text or len(text) < 2:
        issues.append("댓글이 너무 짧습니다 (최소 2자)")
        return issues

    banned = brand.get("banned_keywords", [])
    if isinstance(banned, str):
        try:
            banned = json.loads(banned)
        except (json.JSONDecodeError, TypeError):
            banned = []

    text_lower = text.lower()
    for kw in banned:
        if kw.lower() in text_lower:
            issues.append(f"금지 키워드 포함: {kw}")

    # 광고성 표현 체크
    ad_phrases = ["최고의", "강력 추천", "꼭 써보세요", "지금 바로", "무료 배송", "할인"]
    for phrase in ad_phrases:
        if phrase in text:
            issues.append(f"광고성 표현 포함: {phrase}")

    return issues
