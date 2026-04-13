"""Profile pool bulk generator.

Generates 200+ unique profile assets for the pool:
- avatar: AI-generated or downloaded from free APIs
- banner: Solid color / gradient images
- name: Korean name generator (성+이름 조합)
- description: Claude-generated channel descriptions
- contact: Random email patterns
- hashtag: Topic-based hashtag sets

Usage:
    from hydra.accounts.pool_generator import generate_all
    generate_all(db, count=200)
"""

import hashlib
import json
import random
import struct
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from hydra.core.config import settings
from hydra.core.logger import get_logger
from hydra.db.models import ProfilePool

log = get_logger("pool_generator")

# ─── Korean Names ───

SURNAMES = [
    "김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
    "한", "오", "서", "신", "권", "황", "안", "송", "류", "전",
    "홍", "고", "문", "양", "손", "배", "백", "허", "유", "남",
    "심", "노", "하", "곽", "성", "차", "주", "우", "민", "구",
]

GIVEN_NAMES_FEMALE = [
    "서연", "서윤", "지우", "서현", "민서", "하은", "하윤", "윤서", "지민", "채원",
    "수빈", "지아", "지윤", "은서", "예은", "다은", "수아", "시은", "예린", "소율",
    "유진", "지현", "소영", "미영", "영희", "은정", "수진", "혜진", "민지", "은영",
    "지은", "현정", "미선", "정은", "소연", "유나", "세은", "다인", "예나", "수연",
]

GIVEN_NAMES_MALE = [
    "서준", "도윤", "시우", "예준", "하준", "주원", "지호", "지후", "준서", "민준",
    "건우", "현우", "선우", "우진", "승현", "준호", "시현", "유준", "정우", "승우",
    "민수", "성민", "영수", "동현", "현수", "재영", "준혁", "성호", "민호", "지훈",
    "상우", "태민", "주호", "도현", "진우", "현민", "재민", "지원", "세준", "윤호",
]

# Channel name patterns (not always real names)
CHANNEL_PATTERNS = [
    "{name}의 일상", "{name}TV", "{name} vlog", "{name}의 하루",
    "{name}_{num}", "{hobby}좋아하는{name}", "{name}.official",
    "일상기록_{name}", "{name}의세계", "{name}랑놀자",
    "{hobby}_{num}", "daily_{name}", "{name}의취미생활",
]

HOBBIES = [
    "요리", "여행", "독서", "운동", "게임", "음악", "그림", "사진",
    "캠핑", "등산", "낚시", "뜨개질", "맛집", "카페", "영화", "드라마",
]

# ─── Description templates ───

DESC_TEMPLATES = [
    "안녕하세요 {name}입니다 :) {hobby} 좋아하는 {age}대 {gender}입니다. 일상을 공유합니다.",
    "{hobby}에 관심 많은 평범한 {gender}입니다. 가끔 영상도 올릴게요~",
    "{region}에 사는 {name}입니다. {hobby} 관련 영상을 주로 봐요.",
    "일상 브이로그 | {hobby} | {region} 거주",
    "{hobby} / 일상 / 먹방 | {age}대 {gender} | 소통해요~",
    "별거 없는 일상 기록용 채널입니다 ㅎㅎ",
    "{name} | {hobby} 입문 {year}년차",
    "좋아하는 것: {hobby}, 맛집, 산책 | DM 환영",
    "{region}살이 | {hobby} | 소소한 일상",
    "",  # Empty description (some real channels have none)
]

REGIONS = [
    "서울", "부산", "인천", "대구", "광주", "대전", "수원", "성남",
    "고양", "용인", "안양", "천안", "전주", "청주", "제주",
]


def _random_name(gender: str = None) -> tuple[str, str]:
    """Generate a random Korean name. Returns (full_name, gender)."""
    if not gender:
        gender = random.choice(["male", "female"])
    surname = random.choice(SURNAMES)
    given = random.choice(GIVEN_NAMES_FEMALE if gender == "female" else GIVEN_NAMES_MALE)
    return surname + given, gender


def _random_channel_name() -> str:
    """Generate a random YouTube channel name."""
    name, _ = _random_name()
    pattern = random.choice(CHANNEL_PATTERNS)
    return pattern.format(
        name=name,
        num=random.randint(1, 999),
        hobby=random.choice(HOBBIES),
    )


def _random_description() -> str:
    """Generate a random channel description."""
    name, gender = _random_name()
    tmpl = random.choice(DESC_TEMPLATES)
    if not tmpl:
        return ""
    return tmpl.format(
        name=name,
        gender="여자" if gender == "female" else "남자",
        age=random.choice(["20", "30", "40"]),
        hobby=random.choice(HOBBIES),
        region=random.choice(REGIONS),
        year=random.randint(1, 5),
    )


def _random_email() -> str:
    """Generate a random-looking contact email."""
    name, _ = _random_name()
    # Romanize very roughly
    local = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(5, 10)))
    local += str(random.randint(1, 999))
    domain = random.choice(["gmail.com", "naver.com", "daum.net", "hanmail.net"])
    return f"{local}@{domain}"


def _random_hashtags() -> str:
    """Generate a JSON array of hashtags."""
    count = random.randint(2, 5)
    tags = random.sample(HOBBIES + REGIONS + ["일상", "브이로그", "먹방", "소통", "구독"], count)
    return json.dumps(tags, ensure_ascii=False)


# ─── Avatar/Banner Generation ───

def _generate_avatar(output_dir: Path, index: int) -> str:
    """Generate a unique avatar image (solid color circle on transparent bg).

    Uses pure Python — no external dependencies.
    Creates a simple but unique 200x200 PNG.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"avatar_{index:04d}.png"

    # Generate unique color from index
    h = hashlib.md5(f"avatar_{index}".encode()).digest()
    r, g, b = h[0], h[1], h[2]

    # Create minimal 1x1 PNG with this color (YouTube will resize)
    # For real usage, replace with AI-generated or stock photos
    _write_solid_png(filepath, r, g, b, size=4)

    return str(filepath)


def _generate_banner(output_dir: Path, index: int) -> str:
    """Generate a unique banner image (gradient-like solid color)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"banner_{index:04d}.png"

    h = hashlib.md5(f"banner_{index}".encode()).digest()
    r, g, b = h[3], h[4], h[5]

    _write_solid_png(filepath, r, g, b, size=4)

    return str(filepath)


def _write_solid_png(path: Path, r: int, g: int, b: int, size: int = 4):
    """Write a minimal solid-color PNG file. No external deps."""
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    # IHDR
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    # IDAT — raw pixel data
    raw = b""
    for _ in range(size):
        raw += b"\x00"  # filter: none
        for _ in range(size):
            raw += bytes([r, g, b])
    idat = zlib.compress(raw)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", idat))
        f.write(_chunk(b"IEND", b""))


# ─── AI Avatar Generation (Optional) ───

async def generate_ai_avatars(count: int, output_dir: Path) -> list[str]:
    """Generate realistic avatar images using an external API.

    Options (replace URL with your preferred service):
    1. thispersondoesnotexist.com — free, one at a time
    2. generated.photos API — bulk, paid
    3. Stable Diffusion local — if you have GPU

    Returns list of file paths.
    """
    import httpx

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(count):
            try:
                # thispersondoesnotexist.com returns a random face each time
                resp = await client.get("https://thispersondoesnotexist.com")
                if resp.status_code == 200:
                    filepath = output_dir / f"ai_avatar_{i:04d}.jpg"
                    filepath.write_bytes(resp.content)
                    paths.append(str(filepath))
                    log.info(f"Downloaded AI avatar {i+1}/{count}")
            except Exception as e:
                log.warning(f"AI avatar download failed: {e}")

            # Rate limit — be respectful
            import asyncio
            await asyncio.sleep(2)

    return paths


# ─── Main Generator ───

def generate_all(db: Session, count: int = 200):
    """Generate all pool types in bulk.

    Creates `count` items for each type (name, description, contact, hashtag).
    For avatar/banner, generates simple placeholders — replace with real images.
    """
    asset_dir = Path(settings.data_dir) / "pool_assets"

    stats = {"name": 0, "description": 0, "avatar": 0, "banner": 0, "contact": 0, "hashtag": 0}

    # Check existing to avoid duplicates
    existing_names = {
        p.content for p in
        db.query(ProfilePool.content).filter(ProfilePool.pool_type == "name").all()
    }

    log.info(f"Generating {count} pool items per type...")

    generated_names = set()
    attempts = 0
    while len(generated_names) < count and attempts < count * 3:
        name = _random_channel_name()
        if name not in existing_names and name not in generated_names:
            generated_names.add(name)
        attempts += 1

    for name in generated_names:
        db.add(ProfilePool(pool_type="name", content=name))
        stats["name"] += 1

    for i in range(count):
        # Description
        desc = _random_description()
        db.add(ProfilePool(pool_type="description", content=desc))
        stats["description"] += 1

        # Contact
        email = _random_email()
        db.add(ProfilePool(pool_type="contact", content=email))
        stats["contact"] += 1

        # Hashtags
        tags = _random_hashtags()
        db.add(ProfilePool(pool_type="hashtag", content=tags))
        stats["hashtag"] += 1

        # Avatar (placeholder — replace with real images)
        avatar_path = _generate_avatar(asset_dir / "avatars", i)
        db.add(ProfilePool(pool_type="avatar", content=avatar_path))
        stats["avatar"] += 1

        # Banner (placeholder — replace with real images)
        banner_path = _generate_banner(asset_dir / "banners", i)
        db.add(ProfilePool(pool_type="banner", content=banner_path))
        stats["banner"] += 1

    db.commit()
    log.info(f"Pool generation complete: {stats}")
    return stats
