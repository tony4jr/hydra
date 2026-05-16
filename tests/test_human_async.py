"""Phase 1.5.2 — async 모듈 단위 검증.

mouse_async / keyboard_async / scroll_async 가 async 호출 형태로
동등한 결과를 만드는지 검증.
"""
import random
from typing import Any

import pytest

from hydra.browser.human import (
    HumanConfig, resolve_config,
    AsyncRawMouse, async_human_move, async_human_click, async_human_idle,
    AsyncRawKeyboard, async_human_type,
)


class _AsyncMockMouse:
    def __init__(self):
        self.moves = []
        self.downs = 0
        self.ups = 0
        self.wheels = []

    async def move(self, x: float, y: float) -> None:
        self.moves.append((x, y))

    async def down(self) -> None:
        self.downs += 1

    async def up(self) -> None:
        self.ups += 1

    async def wheel(self, dx: float, dy: float) -> None:
        self.wheels.append((dx, dy))


class _AsyncMockKeyboard:
    def __init__(self):
        self.events = []

    async def down(self, key: str) -> None:
        self.events.append(("down", key))

    async def up(self, key: str) -> None:
        self.events.append(("up", key))

    async def type(self, text: str) -> None:
        self.events.append(("type", text))

    async def insert_text(self, text: str) -> None:
        self.events.append(("insert", text))


@pytest.mark.asyncio
async def test_async_human_move_produces_curve():
    cfg = resolve_config("default")
    raw = _AsyncMockMouse()
    random.seed(99)
    await async_human_move(raw, 50, 50, 400, 300, cfg)
    assert len(raw.moves) >= cfg.mouse_min_steps


@pytest.mark.asyncio
async def test_async_human_click_emits_down_up():
    cfg = resolve_config("default")
    raw = _AsyncMockMouse()
    await async_human_click(raw, is_input=False, cfg=cfg)
    assert raw.downs == 1
    assert raw.ups == 1


@pytest.mark.asyncio
async def test_async_human_idle_no_clicks():
    """idle 은 마우스 이동만, click 없음. 짧은 시간(0.05s)만 실행."""
    cfg = resolve_config("default")
    raw = _AsyncMockMouse()
    # signature: (raw, seconds, cx, cy, cfg)
    await async_human_idle(raw, 0.05, 100.0, 100.0, cfg)
    assert raw.downs == 0
    assert raw.ups == 0


@pytest.mark.asyncio
async def test_async_human_type_ascii():
    """async 도 sync 와 동일 — raw.down/up 으로 ASCII 처리."""
    cfg = resolve_config("default")
    cfg.mistype_chance = 0.0
    cfg.typing_pause_chance = 0.0

    class _FakePage:
        async def evaluate(self, *args, **kw):
            pass
        @property
        def context(self):
            return None

    raw = _AsyncMockKeyboard()
    await async_human_type(_FakePage(), raw, "ab", cfg)
    downs = [e[1] for e in raw.events if e[0] == "down"]
    assert "a" in downs
    assert "b" in downs


@pytest.mark.asyncio
async def test_async_human_type_cjk():
    """async CJK 도 insert_text."""
    cfg = resolve_config("default")
    cfg.mistype_chance = 0.0
    cfg.typing_pause_chance = 0.0

    class _FakePage:
        async def evaluate(self, *args, **kw):
            pass
        @property
        def context(self):
            return None

    raw = _AsyncMockKeyboard()
    await async_human_type(_FakePage(), raw, "안녕", cfg)
    inserted = "".join(e[1] for e in raw.events if e[0] == "insert")
    assert "안" in inserted or "녕" in inserted


@pytest.mark.asyncio
async def test_sync_async_parity_move_count():
    """같은 seed 면 sync/async 가 같은 step 수 생성."""
    from hydra.browser.human import human_move
    cfg = resolve_config("default")

    class _SyncMock:
        def __init__(self):
            self.n = 0
        def move(self, x, y): self.n += 1
        def down(self): pass
        def up(self): pass
        def wheel(self, dx, dy): pass

    sync_raw = _SyncMock()
    random.seed(7)
    human_move(sync_raw, 0, 0, 300, 200, cfg)

    async_raw = _AsyncMockMouse()
    random.seed(7)
    await async_human_move(async_raw, 0, 0, 300, 200, cfg)

    assert sync_raw.n == len(async_raw.moves)
