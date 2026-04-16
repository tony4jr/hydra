"""기본 프리셋 A~J 시드 스크립트.
사용법: python scripts/seed_presets.py
"""
import json
from hydra.db.session import SessionLocal
from hydra.db.models import Preset

SYSTEM_PRESETS = [
    {"name": "씨앗 심기", "code": "A", "description": "단일 시드 댓글 + 좋아요 부스트",
     "steps": [{"step_number": 1, "role": "seed", "type": "comment", "tone": "자연스러운 후기", "target": "main", "like_count": 5, "delay_min": 0, "delay_max": 0}]},
    {"name": "자연스러운 질문 유도", "code": "B", "description": "시드 + 질문자 + 답변 체인",
     "steps": [
         {"step_number": 1, "role": "seed", "type": "comment", "tone": "교육형", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "asker", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
         {"step_number": 3, "role": "seed", "type": "reply", "tone": "추천", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20}]},
    {"name": "동조 여론 형성", "code": "C", "description": "시드 + 다수 동조 대댓글",
     "steps": [
         {"step_number": 1, "role": "seed", "type": "comment", "tone": "후기", "target": "main", "like_count": 20, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 30},
         {"step_number": 3, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 10, "delay_max": 40},
         {"step_number": 4, "role": "witness", "type": "reply", "tone": "경험담", "target": "step_1", "like_count": 5, "delay_min": 15, "delay_max": 45}]},
    {"name": "비포애프터 경험담", "code": "D", "description": "경험자 시드 + 관심 + 추가 정보",
     "steps": [
         {"step_number": 1, "role": "witness", "type": "comment", "tone": "경험담", "target": "main", "like_count": 20, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "curious", "type": "reply", "tone": "호기심", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
         {"step_number": 3, "role": "witness", "type": "reply", "tone": "상세 정보", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20},
         {"step_number": 4, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 10, "delay_max": 35}]},
    {"name": "슥 지나가기", "code": "E", "description": "짧은 캐주얼 단독 댓글",
     "steps": [{"step_number": 1, "role": "fan", "type": "comment", "tone": "캐주얼", "target": "main", "like_count": 5, "delay_min": 0, "delay_max": 0}]},
    {"name": "정보형 교육", "code": "F", "description": "교육형 시드 + 질문 + 정보 제공",
     "steps": [
         {"step_number": 1, "role": "info", "type": "comment", "tone": "교육형", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "asker", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
         {"step_number": 3, "role": "info", "type": "reply", "tone": "정보 제공", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20}]},
    {"name": "남의 댓글 올라타기", "code": "G", "description": "기존 인기 댓글에 대댓글로 진입",
     "steps": [
         {"step_number": 1, "role": "seed", "type": "reply", "tone": "공감+추천", "target": "existing_top", "like_count": 10, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 30}]},
    {"name": "반박 → 중재", "code": "H", "description": "의견 대립 후 중재자가 브랜드 추천",
     "steps": [
         {"step_number": 1, "role": "seed", "type": "comment", "tone": "주장", "target": "main", "like_count": 10, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "asker", "type": "reply", "tone": "반박", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
         {"step_number": 3, "role": "witness", "type": "reply", "tone": "중재+추천", "target": "step_1", "like_count": 15, "delay_min": 10, "delay_max": 35},
         {"step_number": 4, "role": "agree", "type": "reply", "tone": "동조", "target": "step_3", "like_count": 0, "delay_min": 5, "delay_max": 25}]},
    {"name": "간접 경험", "code": "I", "description": "지인 추천 형태의 간접 경험담",
     "steps": [
         {"step_number": 1, "role": "witness", "type": "comment", "tone": "간접 경험", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
         {"step_number": 2, "role": "curious", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
         {"step_number": 3, "role": "witness", "type": "reply", "tone": "상세 답변", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20}]},
    {"name": "숏폼 전용", "code": "J", "description": "숏폼 영상용 짧은 단독 댓글",
     "steps": [{"step_number": 1, "role": "fan", "type": "comment", "tone": "짧은 반응", "target": "main", "like_count": 10, "delay_min": 0, "delay_max": 0}]},
]


def seed():
    db = SessionLocal()
    for p in SYSTEM_PRESETS:
        existing = db.query(Preset).filter(Preset.code == p["code"]).first()
        if existing:
            print(f"  SKIP: {p['code']} ({p['name']}) -- already exists")
            continue
        preset = Preset(
            name=p["name"], code=p["code"], is_system=True,
            description=p["description"],
            steps=json.dumps(p["steps"], ensure_ascii=False),
        )
        db.add(preset)
        print(f"  OK: {p['code']} ({p['name']})")
    db.commit()
    db.close()
    print("\nPreset seeding complete!")


if __name__ == "__main__":
    seed()
