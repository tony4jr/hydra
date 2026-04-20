"""좋아요 부스트 세션 내부 타이밍 설정.

SystemConfig 에서 읽고, 미설정 시 안전한 기본값 반환.
executor 의 _handle_like_boost 가 태스크 시작 시 1회 조회해 사용.
"""
from sqlalchemy.orm import Session

from hydra.db.models import SystemConfig


DEFAULTS = {
    "like_boost.watch_sec_min": 3,
    "like_boost.watch_sec_max": 15,
    "like_boost.scroll_delay_min": 2.0,
    "like_boost.scroll_delay_max": 5.0,
    "like_boost.surrounding_count_min": 2,
    "like_boost.surrounding_count_max": 4,
    "like_boost.click_delay_min": 1.0,
    "like_boost.click_delay_max": 3.0,
}

INT_KEYS = {
    "like_boost.watch_sec_min",
    "like_boost.watch_sec_max",
    "like_boost.surrounding_count_min",
    "like_boost.surrounding_count_max",
}


def load(db: Session) -> dict:
    """DB 에서 전부 읽어 키→값 dict 반환. 없는 키는 기본값 채움.

    음수/역순(min>max) 감지 시 기본값으로 폴백.
    """
    rows = (
        db.query(SystemConfig)
        .filter(SystemConfig.key.in_(DEFAULTS.keys()))
        .all()
    )
    raw = {r.key: r.value for r in rows}

    result: dict = {}
    for key, default in DEFAULTS.items():
        val = raw.get(key)
        if val is None or val == "":
            result[key] = default
            continue
        try:
            if key in INT_KEYS:
                result[key] = int(val)
            else:
                result[key] = float(val)
            if result[key] < 0:
                result[key] = default
        except (TypeError, ValueError):
            result[key] = default

    # 역순 검증 (min>max 인 경우 기본값 쌍으로 복원)
    pairs = [
        ("like_boost.watch_sec_min", "like_boost.watch_sec_max"),
        ("like_boost.scroll_delay_min", "like_boost.scroll_delay_max"),
        ("like_boost.surrounding_count_min", "like_boost.surrounding_count_max"),
        ("like_boost.click_delay_min", "like_boost.click_delay_max"),
    ]
    for lo_key, hi_key in pairs:
        if result[lo_key] > result[hi_key]:
            result[lo_key] = DEFAULTS[lo_key]
            result[hi_key] = DEFAULTS[hi_key]

    return result
