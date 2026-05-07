"""모렉신 브랜드 + 4 타겟(니치) + 9 댓글 트리 프리셋 시드.

PR-8d/8e 의 CommentPreset / CommentTreeSlot + Phase A 의 same_account_as_slot_label
컬럼을 활용. 프리셋 9개는 HTML 미리보기(모렉신 댓글 프리뷰) 기준.

실행:
  cd /opt/hydra
  source .venv/bin/activate
  python scripts/seed_morexin.py
"""
from __future__ import annotations

import json
import sys

from hydra.db.session import SessionLocal
from hydra.db.models import (
    Brand, CommentPreset, CommentTreeSlot, Niche,
)


# ─── 9개 프리셋 ────────────────────────────────────────────
# 각 슬롯: (label, reply_to, same_account_as, length, emoji, ai_var, like_min, like_max, text_template)
PRESETS: list[dict] = [
    {
        "code": "PRESET-001",
        "name": "산후 트렌 원싱크 (F4·L2-L3)",
        "niche_code": "postpartum",
        "description": "산후탈모 고민글 + 자연스러운 답변 흐름",
        "slots": [
            ("A", None, None, "medium", "sometimes", 70, 15, 30,
             "출산하고 머리가 너무 빠져서요... 케라틴 직접 보충이 도움된다는데 진짜인가요? ㅠㅠ"),
            ("B", "A", None, "long", "sometimes", 60, 25, 50,
             "친언니가 조산사인데 체성케라틴 계열이 흡수율 좋다고 하더라구요. 머리카락 80%가 케라틴이라 직접 보충하는 게 효과 좋다고요"),
            ("C", "B", None, "short", "sometimes", 50, 8, 15,
             "저도 그거 4개월째 먹는데 정수리 차이 느껴져요 ㅠㅠ 미용실 가서도 머리숱 늘었다고 하셨어요"),
        ],
    },
    {
        "code": "PRESET-005",
        "name": "산후 의심→오픈 체인 (F7·L1→L4)",
        "niche_code": "postpartum",
        "description": "회의적 첫댓글이 답글에서 설득됨 — 빈도 낮게 운영",
        "slots": [
            ("A", None, None, "medium", "none", 80, 30, 60,
             "산후탈모는 그냥 시간 지나면 돌아온다던데 영양제까지 먹어야 하나요?"),
            ("B", "A", None, "long", "sometimes", 65, 25, 45,
             "저도 그렇게 생각했는데 1년 지나도 안 돌아와서 결국 영양제 먹게 됐어요. 케라틴 직접 보충이 답이더라구요"),
            ("C", "B", None, "medium", "sometimes", 55, 15, 30,
             "맞아요 저도 모렉신 먹고 있어요. 체성케라틴이 동물성이라 그런지 식물성보다 좀 달라요"),
        ],
    },
    {
        "code": "PRESET-008",
        "name": "산후 공감 + 자기답글 (F5·L2-L3)",
        "niche_code": "postpartum",
        "description": "감정 공감 → ASKER 질문 → B가 본인 답글 (D=B 재등장)",
        "slots": [
            ("A", None, None, "short", "often", 75, 10, 25,
             "영상 보고 너무 공감... 저는 산후탈모 너무 심해서 ㅠㅠ"),
            ("B", "A", None, "medium", "sometimes", 60, 15, 30,
             "저 그러다가 체성케라틴 영양제 먹기 시작하고 좋아졌어요"),
            ("C", "B", None, "short", "sometimes", 50, 5, 12,
             "오 어떤거 드세요? 너무 답답해서 알아보는중이에요 ㅠㅠ"),
            ("D", "C", "B", "medium", "sometimes", 55, 8, 18,
             "모렉신이라고 검색해보세요 :) 동물성+식물성 케라틴 같이 들어있어서 흡수가 잘되더라구요"),
        ],
    },
    {
        "code": "PRESET-011",
        "name": "갱년기 트렌 (F4·L2-L3)",
        "niche_code": "menopause",
        "description": "갱년기 고민→답변 흐름",
        "slots": [
            ("A", None, None, "medium", "sometimes", 70, 20, 40,
             "50 넘으니까 머리숱이 진짜 눈에 띄게 줄어요. 미용실 갈 때마다 우울..."),
            ("B", "A", None, "long", "sometimes", 60, 15, 30,
             "저도 그랬는데 케라틴 영양제 챙겨먹고 좀 나아졌어요. 6개월 정도 꾸준히 먹으니까 미용실에서 알아봐 주시더라구요"),
            ("C", "B", None, "medium", "sometimes", 55, 25, 45,
             "그게 체성케라틴이라고 흡수율 좋은 종류가 있어요. 모렉신이 그 계열이고 비오틴까지 같이 들어있어서 편해요"),
        ],
    },
    {
        "code": "PRESET-012",
        "name": "엄마용 추천 Q&A (F2·L3-L4)",
        "niche_code": "menopause",
        "description": "효도템 포지셔닝 — Q&A 1턴",
        "slots": [
            ("A", None, None, "medium", "often", 70, 18, 30,
             "엄마 머리숱 줄어든다고 속상해하셔서 영양제 알아보는 중인데 추천 좀 부탁드려요 ㅠㅠ"),
            ("B", "A", None, "long", "sometimes", 60, 20, 40,
             "저희 엄마도 드시는데 모렉신 좋아하세요. 체성케라틴이라고 머리카락 단백질 직접 보충하는 거고 알약 사이즈도 작아요"),
        ],
    },
    {
        "code": "PRESET-014",
        "name": "의심→오픈 체인 ⚠️저빈도 (F7·L1→L3)",
        "niche_code": "menopause",
        "description": "광고티 의심 댓글이 답글에서 정보로 전환 — 빈도 낮게 운영",
        "slots": [
            ("A", None, None, "medium", "none", 80, 50, 90,
             "영양제 먹어서 머리숱 늘어난 사람 본 적 있나요? 다 뇌피셜 같은데"),
            ("B", "A", None, "long", "none", 65, 30, 60,
             "케라틴 자체를 보충하는 거랑 비타민만 먹는 거랑 차이 커요. 골다공증에 칼슘 먹는 거랑 같은 원리라고 보면 돼요"),
            ("C", "B", None, "medium", "sometimes", 55, 20, 35,
             "저도 한약으로 이것저것 먹었는데 모렉신 6개월 먹고 미용실에서 머리숱 늘었다고 해서 놀라웠어요"),
        ],
    },
    {
        "code": "PRESET-015",
        "name": "정보형 단발 (F1·L2)",
        "niche_code": "menopause",
        "description": "단발 키워드 댓글 — 시장 분위기 조성",
        "slots": [
            ("A", None, None, "medium", "none", 75, 25, 50,
             "머리카락의 80% 이상이 케라틴이라 직접 보충하는 게 핵심이라더군요. 체성케라틴이 흡수율 좋은 종류고요"),
        ],
    },
    {
        "code": "PRESET-021",
        "name": "병원·전문의 키 (F2·L1-L2)",
        "niche_code": "hospital",
        "description": "전문가 톤 — 시장형 분위기",
        "slots": [
            ("A", None, None, "medium", "none", 70, 30, 60,
             "결국 머리카락 자체가 케라틴 단백질이니까 외부 보충이 답인 것 같네요. 영상 덕분에 명확해졌어요"),
            ("B", "A", None, "long", "none", 60, 15, 25,
             "그래서 요즘 체성케라틴이 주목받는 거예요. 칼슘-골다공증과 같은 원리로 직접 보충하는 게 효율적이라 해외 사례가 많아요"),
        ],
    },
    {
        "code": "PRESET-024",
        "name": "뷰티 V-log + 자기답글 (F5·L2-L3)",
        "niche_code": "beauty",
        "description": "30대 데일리 — A질문 → B답 → C묻 → D=B재등장",
        "slots": [
            ("A", None, None, "short", "often", 75, 5, 12,
             "헐 저도 요즘 머리숱 너무 줄어서 고민중인데 ㅠㅠㅠ 영상 너무 도움됐어요"),
            ("B", "A", None, "short", "often", 60, 8, 18,
             "ㅠㅠ 저도 똑같으세요 저도 케라틴 영양제 챙겨먹기 시작했어요"),
            ("C", "B", None, "short", "sometimes", 50, 3, 8,
             "오 어떤거 드세요?? 저도 추천 좀 해주세요"),
            ("D", "C", "B", "medium", "often", 55, 7, 15,
             "체성케라틴 계열이라고 모렉신이라는 건데 괜찮더라구요 :) 한번 검색해보세요!"),
        ],
    },
]

NICHES = [
    ("postpartum", "산후탈모"),
    ("menopause", "갱년기·중년탈모"),
    ("hospital", "병원·전문의"),
    ("beauty", "뷰티·브이로그"),
]


def main(dry: bool = False) -> int:
    db = SessionLocal()
    try:
        # 1) 브랜드
        brand = db.query(Brand).filter_by(name="모렉신").first()
        if not brand:
            brand = Brand(
                name="모렉신",
                product_category="탈모 영양제 / 모근 단백질 보충제",
                core_message="머리카락 80%가 케라틴 — 직접 보충이 답",
                tone_guide="과장 없이 실사용 후기 톤. 1인칭 우선.",
                selling_points=json.dumps([
                    "체성케라틴(동물성) 흡수율 우위",
                    "동물성+식물성 케라틴 동시 함유",
                    "비오틴 동시 배합",
                    "산후·갱년기·일반 탈모 모두 사용",
                ], ensure_ascii=False),
                allowed_keywords=json.dumps([
                    "케라틴", "체성케라틴", "모근 단백질", "비오틴", "두피", "탈모",
                ], ensure_ascii=False),
                banned_keywords=json.dumps([
                    "일라스틴", "엘라스틴",
                    "최고", "무조건", "강추",
                    "공식몰", "할인", "쿠폰",
                    "FDA", "의약품",
                ], ensure_ascii=False),
                mention_rules=json.dumps({
                    "brand_direct": True, "ingredient_only": False
                }, ensure_ascii=False),
                selected_presets="[]",
                preset_video_limit=1,
            )
            db.add(brand)
            db.flush()
            print(f"  ✓ Brand created: {brand.name} (id={brand.id})")
        else:
            print(f"  ⊙ Brand exists: {brand.name} (id={brand.id})")

        # 2) 니치
        niche_map: dict[str, Niche] = {}
        for code, name in NICHES:
            n = db.query(Niche).filter_by(name=name).first()
            if not n:
                n = Niche(name=name, preset_per_video_limit=1, brand_id=brand.id)
                db.add(n); db.flush()
                print(f"  ✓ Niche created: {name} (id={n.id})")
            else:
                print(f"  ⊙ Niche exists: {name} (id={n.id})")
            niche_map[code] = n

        # 3) 프리셋 + 슬롯
        for spec in PRESETS:
            p = db.query(CommentPreset).filter_by(name=spec["name"]).first()
            if p:
                print(f"  ⊙ Preset exists, skip: {spec['code']}")
                continue
            p = CommentPreset(
                name=spec["name"],
                description=f"[{spec['code']}] {spec['description']}",
                is_global=False,
                is_default=False,
            )
            db.add(p); db.flush()

            for i, slot in enumerate(spec["slots"], start=1):
                label, reply_to, same_as, length, emoji, ai_var, lmin, lmax, text = slot
                db.add(CommentTreeSlot(
                    comment_preset_id=p.id,
                    slot_label=label,
                    reply_to_slot_label=reply_to,
                    same_account_as_slot_label=same_as,
                    position=i,
                    text_template=text,
                    length=length,
                    emoji=emoji,
                    ai_variation=ai_var,
                    like_min=lmin,
                    like_max=lmax,
                    like_distribution="adaptive",
                ))

            niche_map[spec["niche_code"]].comment_preset_id = p.id
            print(f"  ✓ Preset {spec['code']}: {len(spec['slots'])} slots → niche={spec['niche_code']}")

        if dry:
            print("\n=== DRY 모드 — rollback ===")
            db.rollback()
        else:
            db.commit()
            print("\n=== 시드 완료 ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    sys.exit(main(dry=dry))
