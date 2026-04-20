"""Claude 없이 슬롯 기반으로 한국인 페르소나 30개 생성 + 저장.

persona_slots 에는 age/gender/region/occupation/device_hint 가 사전 시드됨.
여기서는 각 슬롯에 대해 현실적 한국 페르소나를 템플릿 + 랜덤 풀 조합으로 만들고
DB에 저장. Claude API 호출 없음.

기존 persona_agent 와 출력 스키마 동일 —> 이후 파이프라인(channel_setup, warmup 등)
과 완전 호환.
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hydra.db.session import SessionLocal
from hydra.db.models import Account, PersonaSlot
from hydra.ai.agents.persona_agent import claim_slot
from hydra.accounts.channel_plan import generate_channel_plan

# ─── 이름 풀 (성 + 이름 separate) ────────────────────────────────────

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임",
            "한", "오", "서", "신", "권", "황", "안", "송", "류", "홍"]

MALE_GIVEN = [
    "준호", "민수", "지훈", "태현", "동현", "승우", "성민", "현우", "재훈", "수빈",
    "도영", "시우", "예준", "하준", "주원", "건우", "유찬", "선우", "정우", "승현",
    "태윤", "민재", "준영", "영재", "재원", "석진", "명수", "종현", "우진", "진혁",
]
FEMALE_GIVEN = [
    "지민", "서연", "하은", "서윤", "수빈", "지우", "예은", "다은", "소율", "지아",
    "민지", "은서", "시은", "현서", "채원", "유진", "서영", "수현", "혜원", "지현",
    "예진", "연지", "지은", "해린", "소영", "지수", "윤아", "가은", "미나", "선영",
]

# ─── 직업별 상세 + 관심사 ────────────────────────────────────────────

OCCUPATION_JOBS = {
    "대학생": ["{region} 국립대 경영학과 2학년", "{region} 사립대 미디어커뮤니케이션학과 3학년",
             "{region} 지방대 컴공과 4학년 휴학중", "{region} 소재 대학 심리학과 2학년",
             "{region} 4년제 사회복지학과 3학년", "{region} 2년제 간호학과 2학년"],
    "신입사원": ["{region} 소재 중소기업 마케팅팀", "{region} IT 스타트업 기획팀",
             "{region} 은행 지점 창구", "{region} 유통회사 영업팀"],
    "취업준비생": ["서울 본가, 공무원 시험 준비 1년차", "IT 개발자 전환 부트캠프 수강 중",
               "대기업 채용 준비 2년차", "간호사 국가고시 재도전"],
    "아르바이트": ["카페 바리스타 (주말)", "편의점 야간 아르바이트",
              "배달 라이더 파트타임", "PC방 카운터"],
    "프리랜서": ["웹 디자이너 프리랜서", "SNS 콘텐츠 크리에이터 (초보)",
             "영어 번역 프리랜서"],
    "주부": ["전업 주부, 아이 둘", "맞벌이 휴직 중"],
    "자영업": ["동네 카페 운영 3년차", "온라인 쇼핑몰 운영"],
    "직장인": ["{region} IT 회사 개발자", "{region} 제조업 대리",
            "{region} 서비스업 매니저"],
}

INTERESTS_BY_AGE = {
    "20s": [
        ["축구", "롤(LoL)", "맛집 탐방"],
        ["K-POP", "드라마 정주행", "카페 투어"],
        ["헬스", "프로틴 셰이크", "운동복 쇼핑"],
        ["웹툰", "애니", "굿즈 수집"],
        ["브이로그 시청", "여행 브이로그", "저가항공"],
        ["공부 자극 영상", "인강 리뷰", "자격증"],
        ["패션 하울", "올리브영", "뷰티 튜토리얼"],
        ["카페 디저트", "빵지 순례", "홈베이킹"],
        ["게임 공략", "피파 온라인", "스팀 세일"],
        ["OTT 추천", "넷플릭스 정주행", "왓챠"],
    ],
    "30s": [
        ["등산", "캠핑 장비", "차박"],
        ["재테크", "주식", "ETF"],
        ["육아 정보", "맘카페", "키즈 용품"],
        ["요리 레시피", "백종원", "밀키트"],
        ["자동차 리뷰", "드라이브", "오토 캠핑"],
    ],
    "40s": [
        ["등산", "건강 보조제", "혈압 관리"],
        ["골프 입문", "스크린 골프", "골프 의류"],
        ["부동산", "재개발", "아파트 리뷰"],
        ["자녀 교육", "중학생 학원", "입시 정보"],
    ],
    "50s": [
        ["텃밭", "자연식", "건강 검진"],
        ["트로트", "가요 무대", "임영웅"],
        ["등산", "건강 체조", "국내 여행"],
        ["손주 영상", "가족 여행", "가족 단체방"],
    ],
    "60s": [
        ["트로트", "국악", "가요무대"],
        ["건강 체조", "노인 요가", "아침 산책"],
        ["정치 뉴스", "시사 토크", "종교 방송"],
        ["손주 브이로그", "자녀 가족 영상", "가족 단톡방"],
    ],
}

YT_HABITS_BY_AGE = {
    "20s": "저녁 9시~새벽 1시 주로 사용, 쇼츠 + 10~20분 영상 혼합",
    "30s": "출퇴근 지하철, 점심시간, 밤 10시 아이 재우고 15~30분",
    "40s": "퇴근 후 8~10시, 주말 낮 자차 시청, 롱폼 선호",
    "50s": "저녁 7~10시 TV 옆에서 스마트폰, 음악/트로트 배경 재생",
    "60s": "아침 6~9시, 점심 1~3시, 저녁 8~10시, 대형 폰 화면 선호",
}

SPEECH_STYLES = [
    "친구처럼 반말 섞음, 'ㅋㅋ' 자주",
    "존댓말 유지, 가끔 이모지",
    "짧은 감탄 위주, 느낌표 많음",
    "평어체 덤덤한 어투",
    "'진짜' '대박' 같은 감탄어 섞음",
    "맞춤법 조금 틀려도 개의치 않음",
]

PERSONALITY_SETS = [
    ["유쾌함", "즉흥적", "의리파"],
    ["차분함", "섬세함", "감수성"],
    ["활발함", "호기심 많음", "도전적"],
    ["소심함", "신중함", "관찰력 좋음"],
    ["따뜻함", "배려심", "감성적"],
    ["현실주의", "계획적", "분석적"],
]


def age_bucket(age: int) -> str:
    if age < 30: return "20s"
    if age < 40: return "30s"
    if age < 50: return "40s"
    if age < 60: return "50s"
    return "60s"


def build_persona(slot: PersonaSlot, rng: random.Random) -> dict:
    surname = rng.choice(SURNAMES)
    given = rng.choice(MALE_GIVEN if slot.gender == "male" else FEMALE_GIVEN)
    name = surname + given

    jobs = OCCUPATION_JOBS.get(slot.occupation) or [f"{slot.region} 지역 {slot.occupation}"]
    job = rng.choice(jobs).format(region=slot.region)

    bucket = age_bucket(slot.age)
    interests = rng.choice(INTERESTS_BY_AGE[bucket])
    habits = YT_HABITS_BY_AGE[bucket]

    persona = {
        "age": slot.age,
        "gender": slot.gender,
        "region": slot.region,
        "occupation": slot.occupation,
        "device_hint": slot.device_hint,
        "slot_id": slot.id,
        "name": name,
        "specific_job": job,
        "interests": interests,
        "youtube_habits": habits,
        "speech_style": rng.choice(SPEECH_STYLES),
        "emoji_frequency": rng.choice(["low", "medium", "high"]),
        "comment_length": rng.choice(["short", "short", "medium"]),  # 짧음 선호
        "typo_rate": rng.choice(["low", "medium", "medium"]),
        "personality_keywords": rng.choice(PERSONALITY_SETS),
        # 세션 전체 템포 배수. 0.6(급함) ~ 1.8(느긋함) — 계정마다 봇이 아닌
        # 사람처럼 서로 다른 속도 프로파일을 갖도록.
        "speed_multiplier": round(rng.uniform(0.6, 1.8), 2),
        # 타이핑 스타일 — typist: 한 글자씩 타이핑, paster: clipboard 붙여넣기
        "typing_style": rng.choice(["typist", "typist", "paster"]),
        # 활동량 배수 — 조용한 유저(0.6) vs 활발한 유저(1.5). 스크롤/숏츠 반복 횟수에 곱해짐.
        "activity_multiplier": round(rng.uniform(0.6, 1.5), 2),
    }
    # channel_plan 추가 (기존 로직 재사용)
    persona["channel_plan"] = generate_channel_plan(slot, persona)
    return persona


def main():
    db = SessionLocal()
    try:
        pending = (
            db.query(Account)
            .filter(Account.persona.is_(None))
            .order_by(Account.id)
            .all()
        )
        print(f"Assigning personas to {len(pending)} accounts (no Claude)")
        if not pending:
            return

        for acc in pending:
            try:
                slot = claim_slot(db, acc.id)
            except RuntimeError as e:
                print(f"  #{acc.id} {acc.gmail}: slot claim failed — {e}")
                continue

            # deterministic RNG per slot so reruns give same persona
            rng = random.Random(slot.id * 1000 + acc.id)
            persona = build_persona(slot, rng)
            acc.persona = json.dumps(persona, ensure_ascii=False)
            db.commit()
            print(f"  #{acc.id} {acc.gmail[:38]:38s} → {persona['name']} ({slot.age}세 {slot.gender} {slot.region} {slot.occupation}) / {slot.device_hint}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
