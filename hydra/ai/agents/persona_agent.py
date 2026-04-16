"""Persona generation agent (Sonnet).

Slot-based persona assignment: demographic slots (persona_slots) are
pre-seeded; each slot claimed by one account. Claude fleshes out the
persona using slot constraints (age/gender/occupation/region).
Device_hint on the slot bridges to Layer 1 fingerprint later.
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from hydra.ai.base import get_model, log
from hydra.ai.harness import call_claude, load_prompt, extract_json
from hydra.db.models import Account, PersonaSlot


def claim_slot(db: Session, account_id: int) -> PersonaSlot:
    """Claim an unused demographic slot for this account."""
    slot = (
        db.query(PersonaSlot)
        .filter(PersonaSlot.used.is_(False))
        .order_by(PersonaSlot.id)
        .with_for_update(skip_locked=True)
        .first()
    ) if db.bind.dialect.name != "sqlite" else (
        db.query(PersonaSlot)
        .filter(PersonaSlot.used.is_(False))
        .order_by(PersonaSlot.id)
        .first()
    )
    if not slot:
        raise RuntimeError("No unused persona slots available. Run seed_persona_slots.py.")
    slot.used = True
    slot.assigned_account_id = account_id
    slot.used_at = datetime.now(timezone.utc)
    db.flush()
    return slot


def generate_persona(slot: PersonaSlot) -> dict:
    """Generate a persona using Claude API constrained by slot."""
    gender_display = "여성" if slot.gender == "female" else "남성"
    user_msg = load_prompt(
        "persona_user",
        age=slot.age,
        gender=slot.gender,
        gender_display=gender_display,
        region=slot.region,
        occupation=slot.occupation,
    )

    text = call_claude(
        model=get_model("persona"),
        system="",
        user_message=user_msg,
        max_tokens=700,
        max_retries=2,
    )

    persona = extract_json(text, "{")
    persona["device_hint"] = slot.device_hint  # carry forward for Layer 1
    persona["slot_id"] = slot.id
    # Auto-attach channel plan so every persona ships with a title/handle/avatar plan
    from hydra.accounts.channel_plan import generate_channel_plan
    persona["channel_plan"] = generate_channel_plan(slot, persona)
    log.info(f"Generated persona: slot#{slot.id} {slot.age}세 {slot.gender} {slot.region} {slot.occupation}")
    return persona


def assign_persona(db: Session, account: Account, persona: dict | None = None):
    """Claim a slot and assign Claude-generated persona to the account."""
    if persona is None:
        slot = claim_slot(db, account.id)
        try:
            persona = generate_persona(slot)
        except Exception:
            # Release slot on failure
            slot.used = False
            slot.assigned_account_id = None
            slot.used_at = None
            db.commit()
            raise
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
