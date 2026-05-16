"""Phase 1.5.1 — S 모듈 단위 검증.

config / mouse / keyboard / scroll 의 핵심 함수가 의도대로 분포/형태 생성하는지.
실제 Playwright 호출 X — 순수 알고리즘 검증.
"""
import math
import random
from typing import Any

import pytest

from hydra.browser.human import (
    HumanConfig, resolve_config, merge_config,
    Point, human_move, human_click, click_target, human_idle,
    human_type, SHIFT_SYMBOLS, NEARBY_KEYS,
    rand_range, rand,
)


# ── config ────────────────────────────────────────────────────────────────

def test_default_preset_loads():
    cfg = resolve_config("default")
    assert cfg.typing_delay == 70
    assert 0 < cfg.mistype_chance < 0.1
    assert cfg.mouse_min_steps < cfg.mouse_max_steps
    assert 0 < cfg.mouse_overshoot_chance < 1.0


def test_careful_preset_more_conservative():
    default = resolve_config("default")
    careful = resolve_config("careful")
    # careful = 더 느린 타이핑 + 더 많은 일시정지
    assert careful.typing_delay >= default.typing_delay
    assert careful.typing_pause_chance >= default.typing_pause_chance


def test_merge_config_overrides_only_specified():
    base = resolve_config("default")
    custom = merge_config(base, {"typing_delay": 200})
    assert custom.typing_delay == 200
    assert custom.mouse_min_steps == base.mouse_min_steps  # 변경 안 됨


# ── mouse ─────────────────────────────────────────────────────────────────

class _MockMouse:
    """RawMouse 프로토콜 구현 — 호출 기록만."""
    def __init__(self):
        self.moves = []
        self.downs = 0
        self.ups = 0
        self.wheels = []

    def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    def down(self) -> None:
        self.downs += 1

    def up(self) -> None:
        self.ups += 1

    def wheel(self, dx: float, dy: float) -> None:
        self.wheels.append((dx, dy))


def test_human_move_produces_curve_not_straight_line():
    cfg = resolve_config("default")
    raw = _MockMouse()
    random.seed(42)  # 재현 가능
    human_move(raw, 100, 100, 500, 400, cfg)

    assert len(raw.moves) >= cfg.mouse_min_steps
    # 직선이 아닌지 — 중간 지점이 시작-끝 라인 위에 있지 않음
    mid = raw.moves[len(raw.moves) // 2]
    # 직선 100,100 → 500,400 위에 정확히 있으면 y = 100 + (mid.x - 100) * (300/400)
    expected_y_on_line = 100 + (mid[0] - 100) * (300 / 400)
    deviation = abs(mid[1] - expected_y_on_line)
    assert deviation > 0  # 곡선이라 직선 위에 안 있음


def test_human_move_zero_distance_is_noop():
    cfg = resolve_config("default")
    raw = _MockMouse()
    human_move(raw, 100, 100, 100, 100, cfg)
    assert len(raw.moves) == 0


def test_human_click_emits_down_up():
    cfg = resolve_config("default")
    raw = _MockMouse()
    human_click(raw, is_input=False, cfg=cfg)
    assert raw.downs == 1
    assert raw.ups == 1


def test_click_target_within_box():
    cfg = resolve_config("default")
    box = {"x": 100, "y": 200, "width": 80, "height": 30}
    for _ in range(20):
        pt = click_target(box, is_input=False, cfg=cfg)
        assert 100 <= pt.x <= 180, f"x={pt.x}"
        assert 200 <= pt.y <= 230, f"y={pt.y}"


def test_click_target_input_uses_left_side():
    """input 클릭은 왼쪽 영역(텍스트 시작 위치) 선호."""
    cfg = resolve_config("default")
    box = {"x": 0, "y": 0, "width": 200, "height": 30}
    xs = [click_target(box, is_input=True, cfg=cfg).x for _ in range(50)]
    # input은 left bias — 평균이 왼쪽 절반 안에 있어야
    assert sum(xs) / len(xs) < 100, f"input click 평균 x={sum(xs)/len(xs)}"


# ── keyboard ──────────────────────────────────────────────────────────────

class _MockKeyboard:
    def __init__(self):
        self.events = []

    def down(self, key: str) -> None:
        self.events.append(("down", key))

    def up(self, key: str) -> None:
        self.events.append(("up", key))

    def type(self, text: str) -> None:
        self.events.append(("type", text))

    def insert_text(self, text: str) -> None:
        self.events.append(("insert", text))


def test_shift_symbols_complete():
    """Shift+숫자 + 일반 shift 심볼 모두 포함."""
    assert "!" in SHIFT_SYMBOLS
    assert "@" in SHIFT_SYMBOLS
    assert "?" in SHIFT_SYMBOLS
    assert "~" in SHIFT_SYMBOLS
    assert len(SHIFT_SYMBOLS) >= 20


def test_nearby_keys_qwerty_layout():
    """qwerty 인접 키 매핑 — 알파벳 26개 전부 + 숫자 10개."""
    for ch in "abcdefghijklmnopqrstuvwxyz":
        assert ch in NEARBY_KEYS, f"missing key: {ch}"
        # 인접 키는 자기 자신 아님
        assert ch not in NEARBY_KEYS[ch]
    # 숫자도 포함
    for ch in "0123456789":
        assert ch in NEARBY_KEYS
    # 'q' 의 인접은 'w', 'a' 등 (실제 키보드 위치)
    assert "w" in NEARBY_KEYS["q"] or "a" in NEARBY_KEYS["q"]


def test_human_type_basic_ascii():
    """ASCII 문자열은 raw.down/up 이벤트 발생."""
    cfg = resolve_config("default")
    cfg.mistype_chance = 0.0  # 오타 없음으로 결정적
    cfg.typing_pause_chance = 0.0

    class _FakePage:
        def evaluate(self, *args, **kw): pass
        @property
        def context(self): return None
    raw = _MockKeyboard()
    human_type(_FakePage(), raw, "hi", cfg)
    # ASCII는 down/up 으로 처리 (raw.down(ch) + raw.up(ch))
    downs = [e[1] for e in raw.events if e[0] == "down"]
    assert "h" in downs
    assert "i" in downs


def test_human_type_cjk_uses_insert_text():
    """CJK 는 insert_text 경로."""
    cfg = resolve_config("default")
    cfg.mistype_chance = 0.0
    cfg.typing_pause_chance = 0.0

    class _FakePage:
        def evaluate(self, *args, **kw): pass
        @property
        def context(self): return None
    raw = _MockKeyboard()
    human_type(_FakePage(), raw, "안녕", cfg)
    inserted = [e[1] for e in raw.events if e[0] == "insert"]
    assert "안" in inserted or "안녕" in "".join(inserted)


# ── scroll ────────────────────────────────────────────────────────────────

def test_rand_range_within_bounds():
    """rand_range 가 항상 범위 안 정수 반환."""
    for _ in range(100):
        v = rand_range((50, 150))
        assert 50 <= v <= 150


def test_rand_distribution():
    """rand 분포 — 단순 평균 검사."""
    vals = [rand(0.0, 1.0) for _ in range(1000)]
    avg = sum(vals) / len(vals)
    assert 0.4 < avg < 0.6  # uniform 평균 = 0.5
