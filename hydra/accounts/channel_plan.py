"""Channel plan generator — attached to every persona.

Given a PersonaSlot + optional persona dict, produces a natural-looking
YouTube channel plan: title, handle, description, avatar policy, rename timing.

Variety principles:
- Title style weighted: 본명 35% / 본명_짧음 10% / 영문_본명 12% / 본명_키워드 10%
  / 감성닉 12% / 취미힌트 10% / 영단어닉 6% / 영문_프리픽스 5%
- Handle: NEVER pure name-based; mix of random strings, words, initials, regions, years
- Description: 85% empty, 15% short single-line
- Avatar: 80% default, 20% set_during_warmup with topic (non-face)
- Rename timing: warmup day 2~11 (spread, not clustered)

All randomness seeded by slot.id for reproducibility.
"""

import random
import string
from typing import Any

# Topic -> folder key used by ProfilePool avatar selector
AVATAR_TOPICS_BY_INTEREST = {
    "커피": "coffee",
    "카페": "coffee",
    "캠핑": "garden",
    "꽃": "flower",
    "텃밭": "garden",
    "낚시": "sea",
    "서핑": "sea",
    "달": "moon",
    "밤하늘": "moon",
    "드라마": "flower",
    "등산": "mountain",
    "운동": "flower",
}

KOREAN_SURNAME_TO_INITIAL = {
    "김": "k", "이": "l", "박": "p", "최": "c", "정": "j", "강": "k", "조": "c",
    "윤": "y", "장": "j", "임": "l", "한": "h", "오": "o", "서": "s", "신": "s",
    "권": "k", "황": "h", "안": "a", "송": "s", "전": "j", "홍": "h", "유": "y",
    "고": "g", "문": "m", "손": "s", "양": "y", "배": "b", "백": "b", "허": "h",
    "남": "n", "심": "s", "노": "n", "하": "h", "곽": "g", "성": "s", "차": "c",
    "주": "j", "우": "w", "구": "g", "민": "m", "류": "r", "나": "n", "진": "j",
    "지": "j", "엄": "e", "채": "c", "원": "w", "천": "c", "방": "b", "공": "g",
    "현": "h", "함": "h", "변": "b", "염": "y", "여": "y", "추": "c", "도": "d",
    "소": "s", "석": "s", "선": "s", "설": "s", "마": "m", "길": "g", "연": "y",
    "위": "w", "표": "p", "명": "m", "기": "k", "반": "b", "왕": "w", "금": "g",
    "옥": "o", "육": "y", "인": "i", "맹": "m", "제": "j", "탁": "t", "국": "g",
    "여": "y", "진": "j", "어": "e", "은": "e", "편": "p", "용": "y",
}

KOREAN_NAMES_TO_ROMAJA = {
    # Common patterns; extend as needed. Fallback uses chosung.
    "김": "kim", "이": "lee", "박": "park", "최": "choi", "정": "jung", "강": "kang",
    "조": "cho", "윤": "yoon", "장": "jang", "임": "lim", "한": "han", "오": "oh",
    "서": "seo", "신": "shin", "권": "kwon", "황": "hwang", "안": "ahn", "송": "song",
    "전": "jeon", "홍": "hong", "배": "bae",
}

CITY_SHORT = {
    "서울": "seoul", "경기": "gg", "인천": "inc", "부산": "busan", "대구": "daegu",
    "대전": "dj", "광주": "gj", "울산": "ulsan", "세종": "sejong", "강원": "gw",
    "충북": "cb", "충남": "cn", "전북": "jb", "전남": "jn", "경북": "gb",
    "경남": "gn", "제주": "jeju",
}

KOREAN_FOOD = ["coffee", "latte", "mocha", "bread", "choco", "milk", "tea"]
ENG_WORDS_EMOTIONAL = ["sunny", "cozy", "soft", "dreamy", "mellow", "breeze", "moonlit", "daily"]
ENG_WORDS_HOBBY = ["camper", "hiker", "runner", "angler", "rider", "reader", "gamer", "painter"]

TITLE_STYLES = [
    ("본명", 35),
    ("본명_짧음", 10),
    ("영문_본명", 12),
    ("본명_키워드", 10),
    ("감성닉", 12),
    ("취미힌트", 10),
    ("영단어닉", 6),
    ("영문_프리픽스", 5),
]


def _rand(slot_id: int) -> random.Random:
    return random.Random(slot_id * 7919 + 31)


def _pick_weighted(rng, choices):
    items, weights = zip(*choices)
    return rng.choices(items, weights=weights, k=1)[0]


def _birth_year(age: int) -> int:
    return 2026 - age


def _romanize(korean_name: str) -> str:
    """Very rough: first jamo of surname + first letter Korean to English rules."""
    if not korean_name:
        return ""
    surname = korean_name[0]
    given = korean_name[1:]
    s = KOREAN_NAMES_TO_ROMAJA.get(surname, "")
    g = ""
    for ch in given:
        g += KOREAN_SURNAME_TO_INITIAL.get(ch, ch)
    return (s + g).lower() or "user"


def _build_title(rng, persona: dict, slot) -> tuple[str, str]:
    """Return (title, style_label)."""
    style = _pick_weighted(rng, TITLE_STYLES)
    name = persona.get("name", "") if persona else ""
    occupation = slot.occupation
    region = slot.region
    interests = persona.get("interests", []) if persona else []

    if style == "본명" and name:
        return name, style
    if style == "본명_짧음" and len(name) >= 2:
        return name[1:], style  # 성 떼고 이름만
    if style == "영문_본명" and name:
        roma = _romanize(name)
        capitalized = roma.capitalize() if len(roma) <= 6 else roma[0].upper() + roma[1:]
        # Sometimes add space (Jay Lee), sometimes not (Jihoon)
        if rng.random() < 0.4 and len(name) >= 2:
            given_roma = _romanize(name[1:])
            surname_roma = _romanize(name[0])
            return f"{given_roma.capitalize()} {surname_roma.capitalize()}", style
        return capitalized, style
    if style == "본명_키워드" and name:
        keywords = ["이네", "의 일상", "엄마" if persona.get("gender") == "female" else "아빠", "씨", "의 하루"]
        return f"{name[1:] if len(name) >= 2 else name}{rng.choice(keywords)}", style
    if style == "감성닉":
        pool = ["파도소리", "달빛아래", "커피한잔", "비오는날", "노을풍경", "새벽공기",
                "조용한오후", "책한권", "달콤한밤", "하루끝에"]
        return rng.choice(pool), style
    if style == "취미힌트":
        hint = rng.choice(interests) if interests else occupation
        patterns = [f"{region} {hint}", f"{hint}하는 {occupation[:2]}", f"{hint} 좋아하는"]
        return rng.choice(patterns), style
    if style == "영단어닉":
        return rng.choice(ENG_WORDS_EMOTIONAL + ENG_WORDS_HOBBY).capitalize(), style
    if style == "영문_프리픽스":
        roma = _romanize(name) if name else "user"
        return f"{roma[:2]}_{roma[2:] if len(roma) > 2 else rng.randint(100, 999)}", style

    # Fallback
    return name or "user", style


def _build_handle(rng, persona: dict, slot) -> str:
    """Never purely name-based — mix of random strings, words, initials, years."""
    age = slot.age
    year = _birth_year(age)
    region = slot.region
    name = persona.get("name", "") if persona else ""
    interests = persona.get("interests", []) if persona else []

    patterns = [
        # keyboard random + year
        lambda: "".join(rng.choices(string.ascii_lowercase, k=4)) + str(year),
        # word + year
        lambda: rng.choice(KOREAN_FOOD + ENG_WORDS_EMOTIONAL + ENG_WORDS_HOBBY) + str(year),
        # initials + mmdd
        lambda: "".join([KOREAN_SURNAME_TO_INITIAL.get(c, c) for c in name[:3]]) + f"{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}",
        # chosung + year 2-digit
        lambda: "".join([KOREAN_SURNAME_TO_INITIAL.get(c, c) for c in name[:3]]) + str(year)[-2:],
        # two words
        lambda: rng.choice(KOREAN_FOOD) + "_" + rng.choice(ENG_WORDS_EMOTIONAL),
        # region + year
        lambda: CITY_SHORT.get(region, "kr") + str(year),
        # region + interest word
        lambda: CITY_SHORT.get(region, "kr") + "_" + (rng.choice(ENG_WORDS_HOBBY) if interests else "day"),
        # word + year + role hint
        lambda: rng.choice(ENG_WORDS_HOBBY) + str(year)[-2:] + rng.choice(["", "mom", "dad", ""]),
        # random alphabet 4 + random num 4
        lambda: "".join(rng.choices(string.ascii_lowercase, k=4)) + str(rng.randint(1000, 9999)),
        # short word + year
        lambda: rng.choice(["ms", "gm", "hny", "sjy"]) + str(year)[-4:],
    ]
    handle = rng.choice(patterns)()
    # Sanitize: YouTube handle rules (letters, digits, _ . -)
    handle = "".join(ch for ch in handle.lower() if ch.isalnum() or ch in "._-")
    return handle[:20] or "user" + str(year)


def _build_avatar(rng, persona: dict, slot) -> dict:
    """50% set_during_warmup, 50% default. Topic matched to interests
    (or face when interests don't map to any object topic)."""
    if rng.random() < 0.50:
        interests = persona.get("interests", []) if persona else []
        topic = "flower"
        for kw, t in AVATAR_TOPICS_BY_INTEREST.items():
            if any(kw in i for i in interests):
                topic = t
                break
        return {
            "policy": "set_during_warmup",
            "plan": {
                "topic": topic,
                "set_at_warmup_day": rng.randint(10, 14),
            },
        }
    return {"policy": "default", "plan": None}


def _build_description(rng, persona: dict, slot) -> str:
    """85% empty, 15% single short line drawn from persona."""
    if rng.random() >= 0.15:
        return ""
    interests = persona.get("interests", []) if persona else []
    templates = [
        "관심 있는 영상에 조용히 흔적 남깁니다",
        f"{slot.region}에서 {rng.choice(interests) if interests else '일상'} 좋아하는 {persona.get('age', slot.age)}",
        "그냥 구경만 할게요",
        f"{rng.choice(interests) if interests else '일상'} 좋아요",
    ]
    return rng.choice(templates)


def generate_channel_plan(slot, persona: dict | None = None) -> dict[str, Any]:
    """Build a full channel_plan dict for a given slot + persona."""
    rng = _rand(slot.id)
    title, style = _build_title(rng, persona or {}, slot)
    handle = _build_handle(rng, persona or {}, slot)
    description = _build_description(rng, persona or {}, slot)
    avatar = _build_avatar(rng, persona or {}, slot)
    rename_day = rng.randint(2, 11)

    return {
        "title": title,
        "style": style,
        "handle": handle,
        "description": description,
        "avatar_policy": avatar["policy"],
        "avatar_plan": avatar["plan"],
        "rename_at_warmup_day": rename_day,
    }
