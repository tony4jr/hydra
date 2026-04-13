"""Persona generation and management.

Spec 2.2: Claude generates persona once per account.
Demographics ratio controlled by operator.
"""

import json
import random

import anthropic
from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.db.models import Account

log = get_logger("persona")

# Default demographic distribution (configurable)
DEMOGRAPHIC_WEIGHTS = [
    {"gender": "female", "age_range": (20, 29), "weight": 20},
    {"gender": "female", "age_range": (30, 39), "weight": 30},
    {"gender": "female", "age_range": (40, 49), "weight": 15},
    {"gender": "male", "age_range": (20, 29), "weight": 10},
    {"gender": "male", "age_range": (30, 39), "weight": 15},
    {"gender": "male", "age_range": (40, 49), "weight": 10},
]


def _pick_demographic() -> dict:
    """Pick age/gender based on configured weights."""
    weights = [d["weight"] for d in DEMOGRAPHIC_WEIGHTS]
    choice = random.choices(DEMOGRAPHIC_WEIGHTS, weights=weights, k=1)[0]
    age = random.randint(*choice["age_range"])
    return {"age": age, "gender": choice["gender"]}


def generate_persona(demographic: dict | None = None) -> dict:
    """Generate a persona using Claude API.

    Returns persona dict matching spec 2.2.1 schema.
    """
    if not demographic:
        demographic = _pick_demographic()

    client = anthropic.Anthropic(api_key=settings.claude_api_key)

    prompt = f"""한국인 YouTube 사용자 페르소나를 1개 생성해주세요.

조건:
- 나이: {demographic['age']}세
- 성별: {"여성" if demographic["gender"] == "female" else "남성"}

아래 JSON 형식으로만 답변:
{{
  "age": {demographic['age']},
  "gender": "{demographic['gender']}",
  "region": "한국 도시명",
  "occupation": "직업",
  "interests": ["관심사1", "관심사2", "관심사3"],
  "speech_style": "말투 스타일 설명",
  "emoji_frequency": "low|medium|high",
  "comment_length": "short|medium|long",
  "personality_keywords": ["특성1", "특성2", "특성3"]
}}"""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )

    text = resp.content[0].text.strip()
    # Extract JSON from response
    start = text.index("{")
    end = text.rindex("}") + 1
    persona = json.loads(text[start:end])

    log.info(f"Generated persona: {persona['age']}세 {persona['gender']} {persona['region']}")
    return persona


def assign_persona(db: Session, account: Account, persona: dict | None = None):
    """Assign a persona to an account."""
    if not persona:
        persona = generate_persona()
    account.persona = json.dumps(persona, ensure_ascii=False)
    db.commit()
    log.info(f"Assigned persona to {account.gmail}")


def get_persona(account: Account) -> dict | None:
    """Get parsed persona dict from account."""
    if not account.persona:
        return None
    return json.loads(account.persona)


def batch_assign_personas(db: Session, accounts: list[Account]):
    """Assign personas to multiple accounts."""
    for account in accounts:
        if account.persona:
            continue
        try:
            assign_persona(db, account)
        except Exception as e:
            log.error(f"Persona generation failed for {account.gmail}: {e}")
