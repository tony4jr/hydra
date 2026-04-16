"""Add channel_plan (title, handle, description, avatar, rename_day) to existing personas.

Reads current persona JSON, merges channel_plan block, writes back.
Handle style intentionally varied — NOT always name-based.
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hydra.db.session import SessionLocal
from hydra.db.models import Account

random.seed(42)

# account_id → channel_plan
PLANS = {
    1: {  # 이준호 21 M 광주 대학생
        "title": "준호",
        "handle": "rkds2004",
        "style": "본명_짧음",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 5,
    },
    2: {  # 박민재 22 M 경기 신입
        "title": "커피한잔",
        "handle": "coffee2003",
        "style": "감성닉",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 7,
    },
    3: {  # 김도영 24 M 대구 취준
        "title": "김도영",
        "handle": "ajdn7788",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 3,
    },
    4: {  # 강지훈 22 M 제주 대학생
        "title": "파도소리",
        "handle": "mrgang03",
        "style": "감성닉",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 9,
    },
    5: {  # 정태현 26 M 인천 신입 (러닝/와인)
        "title": "달리는 태현",
        "handle": "run_wine99",
        "style": "취미힌트",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 6,
    },
    6: {  # 장민석 39 M 경북 프리랜서 (캠핑/자동차)
        "title": "장민석",
        "handle": "camper1986",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 4,
    },
    7: {  # 최수진 31 F 부산 마케터
        "title": "달빛아래",
        "handle": "dal_latte",
        "style": "감성닉",
        "description": "",
        "avatar_policy": "set_during_warmup",
        "avatar_plan": {"type": "photo", "subject": "달 / 밤하늘", "set_at_warmup_day": 12},
        "rename_at_warmup_day": 8,
    },
    8: {  # 김예린 30 F 서울 HR
        "title": "김예린",
        "handle": "yrn0515",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 2,
    },
    9: {  # 윤지현 37 F 인천 워킹맘
        "title": "지현이네",
        "handle": "jenny88mom",
        "style": "본명_키워드",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 10,
    },
    10: {  # 이재훈 34 M 판교 카페사장
        "title": "판교 커피",
        "handle": "roaster91",
        "style": "취미힌트",
        "description": "판교에서 커피 내리며 삽니다",
        "avatar_policy": "set_during_warmup",
        "avatar_plan": {"type": "photo", "subject": "원두 클로즈업", "set_at_warmup_day": 11},
        "rename_at_warmup_day": 5,
    },
    11: {  # 한소영 36 F 경기 PM
        "title": "한소영",
        "handle": "hny89",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 3,
    },
    12: {  # 박영미 43 F 부산 분식집
        "title": "남포동 영미",
        "handle": "busan1982",
        "style": "본명_키워드",
        "description": "",
        "avatar_policy": "set_during_warmup",
        "avatar_plan": {"type": "photo", "subject": "꽃 사진", "set_at_warmup_day": 14},
        "rename_at_warmup_day": 6,
    },
    13: {  # 오혜정 47 F 서울 동대문 의류
        "title": "동대문 언니",
        "handle": "ddm_fashion",
        "style": "취미힌트",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 7,
    },
    14: {  # 서지영 42 F 서울 영업부서장
        "title": "서지영",
        "handle": "wine1983",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 4,
    },
    15: {  # 강태수 49 M 서울 본부장
        "title": "강태수",
        "handle": "lead76",
        "style": "본명",
        "description": "관심 있는 영상에 조용히 흔적 남깁니다",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 2,
    },
    16: {  # 배성호 43 M 울산 자동차
        "title": "배성호",
        "handle": "bbs0716",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 9,
    },
    17: {  # 이명숙 59 F 충북 공기업
        "title": "이명숙",
        "handle": "ms1966",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 8,
    },
    18: {  # 김옥자 58 F 전남 주부
        "title": "전남댁 옥자",
        "handle": "suncheon67",
        "style": "본명_키워드",
        "description": "",
        "avatar_policy": "set_during_warmup",
        "avatar_plan": {"type": "photo", "subject": "텃밭/꽃", "set_at_warmup_day": 13},
        "rename_at_warmup_day": 11,
    },
    19: {  # 정순자 57 F 경기 총무
        "title": "정순자",
        "handle": "js68mom",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 5,
    },
    20: {  # 조영식 60 M 강원 은퇴
        "title": "조영식",
        "handle": "wonju1965",
        "style": "본명",
        "description": "",
        "avatar_policy": "default",
        "avatar_plan": None,
        "rename_at_warmup_day": 3,
    },
}


def main():
    db = SessionLocal()
    try:
        updated = 0
        for account_id, plan in PLANS.items():
            account = db.get(Account, account_id)
            if not account or not account.persona:
                print(f"  SKIP a{account_id}: no account/persona")
                continue
            persona = json.loads(account.persona)
            persona["channel_plan"] = plan
            account.persona = json.dumps(persona, ensure_ascii=False)
            updated += 1
            avatar = "avatar" if plan["avatar_policy"] == "set_during_warmup" else "default"
            print(f"  [{updated}/20] a{account_id} title='{plan['title']}' handle='{plan['handle']}' day{plan['rename_at_warmup_day']} {avatar}")
        db.commit()
        print(f"\nDone: {updated} channel plans attached.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
