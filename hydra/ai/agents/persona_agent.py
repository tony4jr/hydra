"""Persona generation agent (Sonnet).

Generates realistic Korean YouTube user personas.
Called once per account during setup.
"""

import json
import random

from sqlalchemy.orm import Session

from hydra.ai.base import get_model, log
from hydra.ai.harness import call_claude, load_prompt, extract_json
from hydra.db.models import Account

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

    gender_display = "여성" if demographic["gender"] == "female" else "남성"
    user_msg = load_prompt(
        "persona_user",
        age=demographic["age"],
        gender=demographic["gender"],
        gender_display=gender_display,
    )

    text = call_claude(
        model=get_model("persona"),
        system="",
        user_message=user_msg,
        max_tokens=500,
        max_retries=2,
    )

    persona = extract_json(text, "{")
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
