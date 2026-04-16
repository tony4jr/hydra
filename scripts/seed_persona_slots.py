"""Seed 200 Korean demographic persona slots.

Distribution reflects Korean YouTube user demographics:
- Age: 20s 25% / 30s 30% / 40s 25% / 50s 15% / 60s 5%
- Gender: 50/50
- Region: 수도권 60% (Seoul/Gyeonggi/Incheon), 광역시 25%, 기타도 15%
- Occupation weighted by age
- Device hint correlates with age
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hydra.db.session import SessionLocal
from hydra.db.models import PersonaSlot

TARGET = 200
random.seed(42)  # deterministic seed

# Age distribution (cumulative allocation)
AGE_PLAN = [
    ((20, 29), 50),  # 25%
    ((30, 39), 60),  # 30%
    ((40, 49), 50),  # 25%
    ((50, 59), 30),  # 15%
    ((60, 65), 10),  # 5%
]

# Region weights (approx Korean population distribution)
REGIONS = [
    ("서울", 40),
    ("경기", 50),
    ("인천", 15),
    ("부산", 15),
    ("대구", 10),
    ("대전", 8),
    ("광주", 7),
    ("울산", 6),
    ("세종", 3),
    ("강원", 6),
    ("충북", 5),
    ("충남", 6),
    ("전북", 5),
    ("전남", 5),
    ("경북", 6),
    ("경남", 7),
    ("제주", 3),
]

# Occupation by age bucket
OCCUPATIONS_BY_AGE = {
    20: [("대학생", 40), ("신입사원", 20), ("프리랜서", 15), ("취업준비생", 15), ("아르바이트", 10)],
    30: [("회사원", 50), ("자영업", 15), ("프리랜서", 15), ("전문직", 10), ("주부", 10)],
    40: [("회사원", 40), ("자영업", 25), ("주부", 15), ("전문직", 10), ("관리자", 10)],
    50: [("자영업", 30), ("회사원", 25), ("주부", 20), ("전문직", 10), ("교사", 8), ("농업", 7)],
    60: [("은퇴", 35), ("자영업", 25), ("주부", 20), ("농업", 15), ("프리랜서", 5)],
}

# Device hint by age (Mac usage decreases with age, Win10 sticks in older users)
DEVICE_HINTS_BY_AGE = {
    20: [("mac_heavy", 45), ("mixed", 35), ("windows_heavy", 20)],
    30: [("mixed", 40), ("windows_heavy", 40), ("mac_heavy", 20)],
    40: [("windows_heavy", 55), ("mixed", 25), ("windows_10_heavy", 15), ("mac_heavy", 5)],
    50: [("windows_10_heavy", 50), ("windows_heavy", 35), ("mixed", 10), ("mac_heavy", 5)],
    60: [("windows_10_heavy", 65), ("windows_heavy", 25), ("mixed", 10)],
}


def weighted_pick(choices):
    items, weights = zip(*choices)
    return random.choices(items, weights=weights, k=1)[0]


def generate_slots():
    slots = []
    for (age_min, age_max), count in AGE_PLAN:
        age_bucket = (age_min // 10) * 10
        occupations = OCCUPATIONS_BY_AGE[age_bucket]
        devices = DEVICE_HINTS_BY_AGE[age_bucket]

        # Force 50/50 gender per age bucket
        genders = ["male"] * (count // 2) + ["female"] * (count - count // 2)
        random.shuffle(genders)

        for g in genders:
            slots.append({
                "age": random.randint(age_min, age_max),
                "gender": g,
                "occupation": weighted_pick(occupations),
                "region": weighted_pick(REGIONS),
                "device_hint": weighted_pick(devices),
            })
    return slots


def seed():
    db = SessionLocal()
    try:
        existing = db.query(PersonaSlot).count()
        if existing > 0:
            print(f"SKIP: {existing} slots already exist. Drop and rerun if you want to reseed.")
            return

        slots = generate_slots()
        for s in slots:
            db.add(PersonaSlot(**s))
        db.commit()
        print(f"Seeded {len(slots)} persona slots")

        # Distribution report
        from collections import Counter
        age_buckets = Counter((s["age"] // 10) * 10 for s in slots)
        gender_dist = Counter(s["gender"] for s in slots)
        device_dist = Counter(s["device_hint"] for s in slots)
        occ_dist = Counter(s["occupation"] for s in slots)
        region_dist = Counter(s["region"] for s in slots)

        print("\n-- Distribution --")
        print(f"Age buckets: {dict(sorted(age_buckets.items()))}")
        print(f"Gender: {dict(gender_dist)}")
        print(f"Device: {dict(device_dist)}")
        print(f"Occupation: {dict(occ_dist.most_common())}")
        print(f"Region top5: {dict(region_dist.most_common(5))}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
