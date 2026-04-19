"""Claude batch 로 검색 키워드 풀을 확장.

data/search_keywords.json 을 로드 → 각 age bucket × sub-theme 조합으로 Claude 호출
→ 새 쿼리 목록 회수 → 기존 풀에 중복 제외하고 append → 저장.

사용 예:
    # 기본 (모든 bucket, 모든 theme, bucket 당 목표 500)
    python scripts/generate_search_pool.py

    # 특정 bucket 만
    python scripts/generate_search_pool.py --buckets 20s,30s

    # 특정 theme 만 (여러 bucket 에 공통 적용)
    python scripts/generate_search_pool.py --themes k-pop,sports

    # 목표 풀 크기 지정 (이미 그보다 많으면 스킵)
    python scripts/generate_search_pool.py --target 800

Claude 호출 건당 50개씩 생성, 중복 제거 후 merge. 총 호출 수는 bucket × theme 조합.
비용: 대략 0.01~0.02$/call, 전체 ≈ $1~2 per run.

실행 전 필요:
    .env 에 CLAUDE_API_KEY=sk-ant-... 설정
"""
import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hydra.core.logger import get_logger

log = get_logger("gen_search_pool")

POOL_PATH = Path("data/search_keywords.json")
CACHE_DIR = Path("data/search_keywords_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ─── bucket × theme 매트릭스 ─────────────────────────────────────────

THEMES = {
    "20s": [
        "K-POP 아이돌 (2026년 4월 현역 그룹 위주: ILLIT, BABYMONSTER, RIIZE, Kiss of Life, BOYNEXTDOOR, ZEROBASEONE, LE SSERAFIM, IVE, KATSEYE, (여자)아이들, 스트레이키즈, 세븐틴, ENHYPEN, NMIXX, ATEEZ, TWS 등. 뉴진스 언급 금지)",
        "한국 축구/해외 리그 (손흥민 토트넘, 이강인 PSG, 김민재 바이에른, 황희찬 울버햄튼, 프리미어리그, 챔피언스리그, K리그, 국가대표)",
        "한국 프로야구 KBO (10개 구단 경기, 순위, 선수)",
        "LoL/발로란트/오버워치/EA FC/배그 등 현역 인기 게임 공략/패치/대회",
        "MMORPG (로스트아크, 메이플스토리, 던파, 디아블로4) + 콘솔 (스위치, 플스5)",
        "서울 맛집 (성수, 연남, 용리단길, 판교, 홍대, 을지로, 강남, 송리단길, 이태원, 압구정)",
        "지방/국내 여행 (제주, 부산, 강릉, 속초, 경주, 전주, 여수)",
        "일본 자유여행 (도쿄, 오사카, 교토, 후쿠오카, 오키나와, 삿포로)",
        "동남아/홍콩/대만 여행 (다낭, 방콕, 세부, 발리, 싱가포르)",
        "유튜버/스트리머 (피식대학, 침착맨, 슈카월드, 홍김동전, 워크맨, 오킹)",
        "올리브영/무신사/에이블리 뷰티 및 패션 쇼핑, 20대 스킨케어/메이크업",
        "토익/자격증/코딩 테스트/공무원 시험 공부법",
        "대학생활 (동아리, 조별과제, 축제, MT, 해외교환)",
        "웹툰/드라마/영화/OTT 추천 (넷플릭스, 디즈니플러스, 티빙, 쿠팡플레이, 왓챠)",
        "피트니스 (헬스, 필라테스, 요가, 러닝, 테니스, 클라이밍, 크로스핏)",
        "연애/썸/소개팅/데이트 코스",
        "자취 요리/자취방 인테리어/가성비 아이템 (다이소, 이케아)",
        "아이폰/갤럭시/맥북/에어팟/아이패드 등 디지털 가전",
        "청년 정책, 청년 월세 지원, 청년 도약 계좌, 청년 적금",
        "페스티벌/콘서트/뮤지컬/전시회/팝업스토어",
        "외국어 공부 (영어, 일본어, 중국어, 스페인어)",
        "반려동물 (강아지, 고양이) 용품/훈련/미용",
        "사진/브이로그/유튜브 크리에이터 장비와 편집",
    ],
    "30s": [
        "ETF/미국 주식/배당주/비트코인 등 재테크",
        "부동산 (청약, 임장, 아파트 시세, 전세 사기)",
        "연금저축/IRP/퇴직연금/실손보험",
        "신생아/유아 육아 (수유, 이유식, 어린이집, 예방접종, 교구)",
        "맘카페 추천템/육아 브이로그/아이 교육",
        "캠핑/글램핑 (경기, 강원, 충남 캠핑장, 장비)",
        "골프 입문/라운딩/골프복/골프장",
        "러닝/마라톤/테니스/자전거/등산 30대",
        "에어프라이어/밀키트/자취요리/베이킹",
        "신차 비교 (캐스퍼, 아이오닉7, EV9, 캐니발, 테슬라, BMW, 벤츠)",
        "이직/연봉협상/퇴사/창업/프리랜서 세금",
        "국내 가족 여행 (제주, 부산, 강릉)",
        "해외 여행 (다낭, 오사카, 싱가포르, 방콕)",
        "홈 인테리어/가전 (세탁기, 냉장고, 에어컨, 로봇청소기)",
        "결혼 준비 (스드메, 혼수, 신혼여행)",
        "부부생활/부모님 선물/효도",
        "30대 패션/향수/헤어/스킨케어",
        "헬스/필라테스/요가/다이어트 30대",
        "건강검진/실손보험/치과/라식",
        "반려동물 (강아지/고양이) 건강관리와 훈련",
    ],
    "40s": [
        "스크린 골프/드라이버/아이언/골프장/골프복",
        "명산 등산 (북한산, 지리산, 설악산, 한라산, 덕유산)",
        "중고등학생 자녀 학원/입시 (대치동, 의대, 수능, 수시)",
        "혈압/혈당/관절/콜레스테롤 관리",
        "40대 체중/근력/유산소 운동",
        "갱년기 관리 (남성/여성), 영양제",
        "재건축/아파트 시세/전세/상가 투자",
        "퇴직연금/배당ETF/노후자금/연금 수령",
        "금/은 투자, 환율, 보험 리모델링",
        "40대 패션/향수/스킨케어/탈모/흰머리",
        "자녀 사춘기 소통/10대 교육",
        "부모 부양/부모님 해외여행/부모님 건강",
        "부부관계 개선/부부 여행/부부 취미",
        "40대 이직/임원 승진/명퇴/창업",
        "중고차/차량 보험/블랙박스/정비",
        "수입차 유지비/BMW/벤츠/아우디",
    ],
    "50s": [
        "트로트 (임영웅, 영탁, 김호중, 송가인, 가요무대, 미스터트롯/미스트롯)",
        "7080 가요/통기타/추억의 가요",
        "관절염/혈압약/당뇨/갱년기/콜레스테롤",
        "국내 힐링 여행 (제주, 강원도, 경주, 전주, 보성)",
        "효도 관광/해외 패키지 (유럽, 일본, 동남아)",
        "등산 모임/50대 둘레길/체력 관리",
        "텃밭/주말농장/화초 키우기",
        "노후 연금/상속세/증여세/주택연금",
        "부동산 세금/양도세/종부세/1주택 특례",
        "자녀 결혼 준비/혼수 비용/청첩장",
        "손주 선물/손주와 여행",
        "50대 패션/헤어/스킨케어/탈모",
        "시니어 헬스/요가/걷기 운동",
        "은퇴 준비/은퇴 후 취미/은퇴 집 인테리어",
        "재래시장/노포/국내 맛집 당일치기",
    ],
    "60s": [
        "트로트/가요무대/열린음악회/1970-80 가요",
        "노인 요가/치매 예방 운동/관절 강화 체조",
        "혈압/혈당/고지혈증/백내장/녹내장/청력",
        "한국사 다큐/조선왕조실록/역사 야사",
        "스님 설법/교회 설교/찬송가/명상 음악",
        "자연 다큐/힐링 영상/파도 소리/빗소리",
        "손주 영상/손주 선물/가족 모임",
        "기초연금/연금 개혁/시니어 정책/노인 일자리",
        "실버타운/요양보험/장기요양",
        "바둑/장기/서예/시조/난초/분재/화초",
        "환갑/칠순/팔순 잔치/제사 음식/가족 행사",
        "시니어 건강식/저염식/유산균",
        "시니어 여행/효도 관광/단체 관광",
        "시니어 스마트폰 사용법/유튜브 기초",
    ],
}

SYSTEM_PROMPT = """당신은 한국 유튜브 검색 트렌드 전문가입니다.
실제 한국인이 유튜브에서 자연스럽게 검색할 만한 키워드/문구를 생성해주세요.

요구사항:
- 한국어로
- 자연스러운 검색 문구 (너무 격식체 X, 약어/줄임말 적극 사용)
- 다양한 길이 (2~7 단어)
- 중복 최소화, 서로 다른 각도의 쿼리
- 현역/최신 (2026년 4월 기준), 철지난 레퍼런스 금지
- 출력은 JSON 배열 형식만 (설명 없이): ["쿼리1","쿼리2",...]
"""


def _call_claude(bucket_label: str, theme: str, count: int = 50) -> list[str]:
    """Claude Sonnet 호출 → 쿼리 리스트 회수."""
    from anthropic import Anthropic
    client = Anthropic()
    user_msg = (
        f"[타겟]: {bucket_label} 한국인\n"
        f"[주제]: {theme}\n"
        f"[개수]: 정확히 {count}개\n\n"
        f"위 조건에 맞는 유튜브 검색 쿼리 {count}개를 JSON 배열로만 출력하세요."
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = resp.content[0].text.strip()
    # strip ```json fences if any
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL)
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        log.warning(f"invalid JSON from Claude for {bucket_label}/{theme[:30]}")
        return []
    if not isinstance(items, list):
        return []
    return [str(x).strip() for x in items if str(x).strip()]


def _cache_key(bucket: str, theme: str) -> Path:
    slug = re.sub(r"[^\w가-힣]+", "_", theme)[:80]
    return CACHE_DIR / f"{bucket}__{slug}.json"


def expand_bucket(bucket: str, themes: list[str], per_theme: int, pool: list[str]) -> int:
    existing = set(pool)
    added = 0
    for theme in themes:
        cache_file = _cache_key(bucket, theme)
        if cache_file.exists():
            cached = json.loads(cache_file.read_text())
        else:
            log.info(f"[{bucket}] calling Claude for theme: {theme[:60]}")
            try:
                cached = _call_claude(f"{bucket} ({bucket[:-1]}대)", theme, count=per_theme)
            except Exception as e:
                log.error(f"Claude failed for {bucket}/{theme[:40]}: {e}")
                continue
            cache_file.write_text(json.dumps(cached, ensure_ascii=False, indent=2))
            time.sleep(1.0)  # rate limit safety

        new_items = [q for q in cached if q not in existing]
        existing.update(new_items)
        pool.extend(new_items)
        added += len(new_items)
        log.info(f"  +{len(new_items)} (total {len(pool)})")
    return added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--buckets", help="comma-separated list, default=all",
                        default=",".join(THEMES.keys()))
    parser.add_argument("--themes", help="substring match, applies to all buckets")
    parser.add_argument("--target", type=int, default=500,
                        help="skip bucket if already at/over this size")
    parser.add_argument("--per-theme", type=int, default=50,
                        help="queries to request per Claude call")
    args = parser.parse_args()

    if not os.getenv("CLAUDE_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("Set CLAUDE_API_KEY or ANTHROPIC_API_KEY in .env")

    pool = json.loads(POOL_PATH.read_text())
    buckets = [b.strip() for b in args.buckets.split(",") if b.strip()]

    for bucket in buckets:
        if bucket not in THEMES:
            log.warning(f"unknown bucket: {bucket}")
            continue
        current = pool.get(bucket, [])
        if len(current) >= args.target:
            log.info(f"[{bucket}] already {len(current)} >= target {args.target}, skipping")
            continue

        themes = THEMES[bucket]
        if args.themes:
            needle = args.themes.lower()
            themes = [t for t in themes if needle in t.lower()]
            if not themes:
                log.warning(f"no themes matching {args.themes!r} in {bucket}")
                continue

        log.info(f"[{bucket}] current={len(current)}, target={args.target}, themes={len(themes)}")
        added = expand_bucket(bucket, themes, args.per_theme, current)
        pool[bucket] = current
        log.info(f"[{bucket}] +{added} added, now {len(current)}")

        # persist after each bucket
        POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2))

    log.info("done")


if __name__ == "__main__":
    main()
