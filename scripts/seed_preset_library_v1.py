"""G-T1~T10 글로벌 프리셋 라이브러리 시드 (PR-C v1).

10개 프리셋, 슬롯 33개. 의도 설명형 + tone_anchor + 슬롯별 mention 정책.
모렉신 노출은 G-T4/T7/T9/T10 의 마지막 자기답글 슬롯에서만.

운영 가중치는 Niche 의 NichePresetSelection.weight 로 조정.
"""
from __future__ import annotations
import json
import sys

from hydra.db.session import SessionLocal
from hydra.db.models import CommentPreset, CommentTreeSlot


# 슬롯 fields: (label, reply_to, same_acct, length, emoji, ai_var, lmin, lmax, mention_brand, mention_solution, intent, tone_anchor_list)
PRESETS: list[dict] = [
    # ── G-T1: 메인 공감 + 답글 케라틴 정보 (2슬롯) ───
    {
        "code": "G-T1",
        "name": "G-T1 메인공감 + 답글케라틴 (2슬롯)",
        "description": "기본형. 메인 공감 좋아요 부스트, 답글에서 케라틴 정보. 모렉신 X.",
        "slots": [
            ("A", None, None, "medium", "sometimes", 88, 30, 80, False, False,
             "[메인·강한 공감] 영상 주제 본인 입장에서 진심 공감. 1-2 문장. 제품·키워드 일체 X. 본인 상황(산후/갱년기/30대 등)만 살짝.",
             ["ㅠㅠ 영상 보면서 진짜 위로받았어요... 저도 산후 5개월차예요",
              "와 이 영상 진짜 공감되네요 매일 미용실 가기 무서웠는데"]),
            ("B", "A", None, "medium", "sometimes", 85, 5, 15, False, False,
             "[짧은 정보] 메인에 동조 + 머리카락이 케라틴이라더라 사실 한 줄. 제품 X. '알아보니' / '들어보니' 톤.",
             ["ㅠㅠ 저도 똑같아요. 알아보니까 머리카락이 거의 케라틴이라더라구요",
              "맞아요. 머리카락이 단백질 덩어리라 외부 케어로는 한계라던데..."]),
        ],
    },
    # ── G-T2: 메인 회의 + 답글 차별화 (2슬롯) ───
    {
        "code": "G-T2",
        "name": "G-T2 메인회의 + 답글차별화 (2슬롯)",
        "description": "회의형 메인이 좋아요 잘 받음. 답글에서 먹어야 답이라는 메커니즘.",
        "slots": [
            ("A", None, None, "medium", "none", 85, 50, 150, False, False,
             "[메인·솔직한 회의] 비싼 헤어케어 제품 다 써봤는데 별로였다는 한 마디. 구체 제품명 X. 솔직·답답한 톤.",
             ["샴푸도 두피앰플도 비싼거 다 써봤는데 솔직히 별 차이 없던데요 ㅠㅠ",
              "트리트먼트 두피케어 다 해봐도 머리 빠지는건 똑같던데..."]),
            ("B", "A", None, "long", "none", 80, 8, 20, False, False,
             "[부드러운 정보] 외부 케어 한계 + 머리카락이 케라틴이라 먹어야 의미있다. 외국 논문 가벼운 언급. 가르치는 톤 X. 본인도 그랬던 톤. 체성케라틴 X.",
             ["저도 그랬는데 알아보니까 머리카락 자체가 단백질이라 바르는 건 한계더라구요. 케라틴 직접 먹는 게 메커니즘이 맞다고 외국 논문에서도 봤어요"]),
        ],
    },
    # ── G-T3: 메인 회의 + 답글 차별화 + 자기답 본인경험 (3슬롯, 체성케라틴 등장) ───
    {
        "code": "G-T3",
        "name": "G-T3 회의 → 차별화 → 체성케라틴 (3슬롯)",
        "description": "체성케라틴 첫 등장. 모렉신 X.",
        "slots": [
            ("A", None, None, "medium", "none", 85, 50, 120, False, False,
             "[메인·회의] 영양제·헤어케어에 회의적인 한 마디. 본인 시도 경험도 OK.",
             ["영양제 비타민 다 먹어봤는데 머리 늘어난 사람 본 적 없는데요",
              "한약까지 해봤는데 그냥 시간이 약인거 같아요"]),
            ("B", "A", None, "long", "none", 80, 10, 25, False, True,
             "[정보·메커니즘] A에 부드럽게 반박. 비타민과 케라틴 직접 보충은 다르다. 체성케라틴 처음 등장. 외국 논문 가벼운 언급.",
             ["저도 그렇게 생각했는데 비타민이랑 케라틴 직접 보충은 좀 달라요. 머리카락 자체가 케라틴이라 그걸 직접 쓰는 게 메커니즘이 다르대요. 체성케라틴이 흡수 좋다고 하더라구요"]),
            ("C", "B", None, "short", "sometimes", 85, 5, 12, False, True,
             "[짧은 동조 + 경험] B의 정보에 동의. 본인도 체성케라틴 챙기고 좀 좋아짐. 모렉신 X. 효능 단정 회피.",
             ["맞아요 저도 체성케라틴 챙기고 좀 다르더라구요",
              "오 저도 그래서 체성케라틴 먹기 시작했는데 6개월쯤 됐어요"]),
        ],
    },
    # ── G-T4: 메인 공감 + 답글 + 자기답 호기심 + 자기답 회피 (4슬롯) ───
    {
        "code": "G-T4",
        "name": "G-T4 공감 → 키워드 → 호기심 → 회피 (4슬롯)",
        "description": "B가 C의 호기심에 답하지만 제품명은 일부러 회피. 체성케라틴 성분만 강조 → 신뢰도 ↑ 검색 유도.",
        "slots": [
            ("A", None, None, "medium", "often", 88, 40, 100, False, False,
             "[메인·강한 감정] 영상에 깊은 공감. 본인 상황 살짝.",
             ["ㅠㅠ 저도 너무 똑같아요. 이 영상 보면서 펑펑 울었어요"]),
            ("B", "A", None, "medium", "sometimes", 85, 8, 18, False, True,
             "[동조 + 키워드] A에 공감하면서 체성케라틴 좋다고 들었다는 톤. 본인 시작했다는 짧은 언급.",
             ["저도 똑같았어요 ㅠ 저는 요즘 체성케라틴 먹기 시작했는데 좀 다르더라구요"]),
            ("C", "B", "A", "short", "often", 85, 3, 8, False, True,
             "[짧은 호기심] 메인 작성자가 자기답글로 호기심 표시. '오 그게 뭐에요?' / '어디서 사요?' / '뭐 드세요?'.",
             ["오 그게 뭐에요? 처음 들어봐요",
              "체성케라틴 어디서 살 수 있어요?",
              "뭐 드시는데요?"]),
            ("D", "C", "B", "medium", "sometimes", 80, 5, 12, False, True,
             "[친절한 회피·신뢰도] B 자기답. C 질문에 답하지만 제품명은 일부러 회피. '광고같아서' / '특정 제품 추천은 좀 그래서' 류. 체성케라틴 성분 강조. 외국 논문 가벼운 언급 OK. 강요 X. 모렉신 등장 X.",
             ["제품명 말씀드리긴 광고같아서 좀 그래요 ㅠ 체성케라틴이라는 성분 검색해보시면 나와요",
              "특정 제품 추천은 좀 그렇고요... 체성케라틴이 핵심 성분이래요. 외국 논문 보면 케라틴 직접 먹는게 답이라더라구요",
              "광고처럼 보일까봐 제품은 못 말씀드리겠고요, 그냥 체성케라틴 검색해보세요!",
              "음 제품명은 살짝 부담스러워서요 ㅎㅎ 체성케라틴이라는 거 알아보시면 좋을 것 같아요"]),
        ],
    },
    # ── G-T5: 메인 관점 + 답글 전문가 정보 (2슬롯) ───
    {
        "code": "G-T5",
        "name": "G-T5 관점 + 전문가 정보 (2슬롯)",
        "description": "전문직 페르소나용. 논문 근거 강조. 모렉신 X.",
        "slots": [
            ("A", None, None, "medium", "none", 80, 30, 70, False, False,
             "[메인·관점] 영상 잘 봤다는 톤 + 본인 의견. 제품·키워드 X. 영상 주제 정리하는 톤.",
             ["결국 외부 케어로는 한계가 있다는 걸 다시 느끼네요. 영상 잘 봤습니다",
              "근본적으로 영양 보충이 핵심이라는 영상이네요. 잘 정리해주셔서 감사해요"]),
            ("B", "A", None, "long", "none", 75, 8, 20, False, True,
             "[전문가 톤 정보] A 동조 + 케라틴/체성케라틴 메커니즘. 한의사·약사·영양사 페르소나에 잘 맞음. 논문 근거 강조. 모렉신 X.",
             ["맞습니다. 머리카락이 케라틴 단백질이라 외부 케어 한계가 명확하죠. 해외에서는 체성케라틴 직접 보충이 흡수 메커니즘 측면에서 효율적이라는 연구 사례가 누적되고 있어요"]),
        ],
    },
    # ── G-T6: 다중 메인 — 공감/답글 + 키워드 단발 (4슬롯, 2 트리) ───
    {
        "code": "G-T6",
        "name": "G-T6 다중메인 (공감트리 + 키워드단발)",
        "description": "한 영상 두 트리. 영상 활성도 무관 사용 가능.",
        "slots": [
            ("A", None, None, "medium", "often", 88, 40, 100, False, False,
             "[메인1·공감] G-T1 의 A 와 동일 톤.",
             ["ㅠㅠㅠ 영상 보고 진짜 위로받음. 저만 그런게 아니구나 싶어서"]),
            ("B", "A", None, "medium", "sometimes", 85, 5, 15, False, False,
             "[짧은 정보] A에 동조 + 케라틴 사실.",
             ["저도 똑같아요. 머리카락이 케라틴이라더라구요. 영양 보충이 답이래요"]),
            ("C", None, None, "short", "sometimes", 85, 15, 35, False, True,
             "[메인2·키워드 단발] 다른 페르소나가 별개 댓글로 체성케라틴 짧게 언급. 좋아요보다 키워드 노출 목적.",
             ["요즘 체성케라틴 좋다는 얘기 많이 들리네요. 저도 시작해보려구요",
              "친구가 체성케라틴 추천하던데 영상 보고 더 마음 굳어짐"]),
        ],
    },
    # ── G-T7: 다중 메인 — 회의/답글 + 본인경험/호기심/모렉신 (5슬롯, 2 트리) ───
    {
        "code": "G-T7",
        "name": "G-T7 다중메인 (회의트리 + 회피트리)",
        "description": "두 트리. E 슬롯에서 제품 회피로 신뢰도 ↑.",
        "slots": [
            ("A", None, None, "medium", "none", 85, 50, 130, False, False,
             "[메인1·회의] G-T2 회의 톤.",
             ["비싼 헤어케어 제품 다 써봐도 머리 빠지는건 똑같던데..."]),
            ("B", "A", None, "long", "none", 80, 8, 18, False, False,
             "[정보·먹어야] 케라틴 직접 보충 메커니즘. 체성케라틴 X.",
             ["저도 그랬는데 머리카락 자체가 단백질이라 바르는건 한계라더라구요. 직접 먹는 게 답이래요"]),
            ("C", None, None, "medium", "sometimes", 85, 20, 50, False, True,
             "[메인2·짧은 경험] 본인이 체성케라틴 챙기고 좋아짐.",
             ["저는 체성케라틴 먹고 6개월차인데 미용실에서 머리숱 늘었다고 하시더라구요"]),
            ("D", "C", None, "short", "often", 85, 3, 8, False, False,
             "[짧은 호기심] '오 어떤거 드세요??' 류.",
             ["오 어떤거 드세요?? 저도 추천 좀요"]),
            ("E", "D", "C", "medium", "sometimes", 80, 4, 10, False, True,
             "[친절한 회피] C 자기답. D 호기심에 답하지만 제품명 회피. 체성케라틴 성분 강조. 광고같아서 못 말한다 톤.",
             ["제품명은 광고같아서 좀 그렇고요... 체성케라틴이 들어있는 거 찾아보시면 돼요. 외국 논문도 케라틴 직접 보충이 답이라고 하더라구요",
              "특정 제품 추천하긴 좀 그래서요 ㅠ 체성케라틴이라는 성분 검색해보시면 나오는 게 있어요"]),
        ],
    },
    # ── G-T8: 다중 메인 — 회의/답글 + 정보단발 + 짧은공감 (4슬롯, 3 트리) ───
    {
        "code": "G-T8",
        "name": "G-T8 다중메인 (회의 + 정보 + 공감)",
        "description": "세 트리. 자연 분포 분위기. 모렉신 X.",
        "slots": [
            ("A", None, None, "short", "none", 85, 40, 100, False, False,
             "[메인1·회의] 헤어케어 제품 회의.",
             ["샴푸 비싼거 써도 효과 모르겠던데..."]),
            ("B", "A", None, "medium", "none", 80, 5, 15, False, False,
             "[정보·먹어야] 케라틴 직접 보충.",
             ["맞아요. 결국 머리카락이 케라틴이라 안에서 보충하는게 답이래요"]),
            ("C", None, None, "short", "none", 85, 18, 35, False, True,
             "[메인2·정보 단발] '체성케라틴 좋다더라' 짧게.",
             ["요즘 체성케라틴 흡수율 좋다고 하더라구요. 영상 잘 봤습니다"]),
            ("D", None, None, "short", "often", 88, 25, 60, False, False,
             "[메인3·짧은 공감] 1문장.",
             ["와 영상 보고 위로받았어요... 저도 갱년기라 ㅠ"]),
        ],
    },
    # ── G-T9: 메인 + 자기답 정보 + 호기심 + 자기답 모렉신 (4슬롯) ───
    {
        "code": "G-T9",
        "name": "G-T9 자기답 정보 → 호기심 → 회피 (4슬롯)",
        "description": "메인 작성자가 자기답으로 정보 보강 → 다른 사람 호기심 → 자기답으로 제품 회피·체성케라틴 강조.",
        "slots": [
            ("A", None, None, "medium", "sometimes", 85, 35, 80, False, False,
             "[메인·관점] 영상 정리하는 톤 + 본인 상황. 키워드 X.",
             ["결국 영양 보충이 핵심이라는거네요. 저도 산후 6개월차인데 다시 알아봐야겠어요"]),
            ("B", "A", "A", "medium", "sometimes", 80, 5, 12, False, True,
             "[자기답·정보 보강] 메인 작성자가 자기답으로 추가 정보. 케라틴 + 체성케라틴 짧게.",
             ["찾아봤는데 머리카락이 거의 케라틴이라 직접 먹는게 답이래요. 체성케라틴이라는 게 흡수 좋다는데 알아봐야겠네요"]),
            ("C", "B", None, "short", "often", 85, 3, 8, False, False,
             "[짧은 관심] B의 정보에 다른 사용자가 관심 표시.",
             ["오 저도 알아보고싶어요. 어디서 사요?"]),
            ("D", "C", "A", "medium", "sometimes", 80, 4, 10, False, True,
             "[친절한 회피] A 자기답. C 호기심에 답하지만 제품명 회피. 체성케라틴 성분만 강조. 본인이 검색해서 알아보는 톤도 OK.",
             ["저도 검색해봤는데 제품명 추천하긴 좀 그렇고... 체성케라틴이라는 성분이 들어있는 거더라구요. 외국 논문 보니까 직접 보충이 답이래요",
              "여러 제품이 있던데 특정 제품 추천하긴 그래서 ㅠ 체성케라틴 검색해보시면 나와요"]),
        ],
    },
    # ── G-T10: 깊은 자기답 체인 (5슬롯) ───
    {
        "code": "G-T10",
        "name": "G-T10 깊은 자기답 체인 (5슬롯)",
        "description": "회의→정보→자기답경험→메인전향→회피마무리. 매우 가끔.",
        "slots": [
            ("A", None, None, "medium", "sometimes", 85, 60, 150, False, False,
             "[메인·강한 감정 + 회의] 영상 공감하면서 본인은 영양제 다 별로였다는 톤.",
             ["ㅠㅠ 영상 너무 공감... 근데 솔직히 영양제 다 먹어봐도 그게 그거 같아요"]),
            ("B", "A", None, "long", "none", 80, 10, 25, False, False,
             "[부드러운 정보] 비타민·비오틴은 한계, 케라틴 직접 보충 메커니즘.",
             ["비타민이랑 케라틴 직접 보충은 좀 달라요. 머리카락이 케라틴이라 그걸 직접 먹는 메커니즘이라더라구요"]),
            ("C", "B", "B", "medium", "sometimes", 80, 5, 12, False, True,
             "[자기답·본인 경험] B 작성자 자기답글로 본인 체성케라틴 경험 추가.",
             ["저는 그래서 체성케라틴 먹기 시작하고 6개월쯤 됐는데 미용실에서 머리숱 늘었다고 하시더라구요"]),
            ("D", "C", "A", "short", "often", 85, 3, 8, False, False,
             "[메인 작성자 전향] A가 회의했지만 B/C 의 정보·경험에 마음 흔들림. 자연 호기심.",
             ["오 정말요? 그게 그렇게 다른가요... 저도 한번 알아봐야겠네요"]),
            ("E", "D", "B", "medium", "sometimes", 80, 4, 10, False, True,
             "[친절 마무리·회피] B 가 D 에게 답. 제품명 회피. 체성케라틴 성분 강조. 본인 만족 짧게.",
             ["제품명 추천하긴 광고같아서 좀 그렇고요 ㅎ 체성케라틴 검색해보세요. 외국 논문 봐도 케라틴 직접 보충이 메커니즘 답이라고 해서 저는 만족중이에요",
              "특정 제품 말하긴 좀 그래서요 ㅠ 체성케라틴이라는 성분으로 알아보시면 돼요. 저는 이거 시작하고 좋아졌어요"]),
        ],
    },
]


def main(dry: bool = False) -> int:
    db = SessionLocal()
    try:
        for spec in PRESETS:
            existing = db.query(CommentPreset).filter_by(name=spec["name"]).first()
            if existing:
                print(f"⊙ exists, skip: {spec['code']}")
                continue
            p = CommentPreset(
                name=spec["name"],
                description=f"[{spec['code']}] {spec['description']}",
                is_global=True,
                is_default=False,
            )
            db.add(p); db.flush()
            for i, slot in enumerate(spec["slots"], start=1):
                (label, reply_to, same_acct, length, emoji, ai_var,
                 lmin, lmax, mention_brand, mention_solution, intent,
                 anchor_list) = slot
                db.add(CommentTreeSlot(
                    comment_preset_id=p.id,
                    slot_label=label, reply_to_slot_label=reply_to,
                    same_account_as_slot_label=same_acct,
                    position=i,
                    intent=intent,
                    tone_anchor=json.dumps(anchor_list, ensure_ascii=False),
                    mention_brand=mention_brand,
                    mention_solution=mention_solution,
                    text_template=None,  # PR-C: 의도 설명형, text_template X
                    length=length, emoji=emoji, ai_variation=ai_var,
                    like_min=lmin, like_max=lmax, like_distribution="adaptive",
                ))
            print(f"✓ {spec['code']}: {len(spec['slots'])} 슬롯")

        if dry:
            db.rollback()
            print("\n[DRY] rollback")
        else:
            db.commit()
            print("\n=== 시드 완료 (10 프리셋) ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(dry="--dry" in sys.argv))
