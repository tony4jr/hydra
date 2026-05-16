"""hydra.browser.human — 인간 행동 시뮬레이션 레이어.

Origin: CloakBrowser (https://github.com/CloakHQ/CloakBrowser) MIT licensed.
포팅 범위: human/ 모듈만. binary/geoip/examples는 제외 (AdsPower와 중복 또는 무관).

Phase 1.5 — config/mouse/keyboard/scroll 의 4개 S 모듈 우선.
async 버전, actionability, patch_page wiring 은 후속 step.
"""
from hydra.browser.human.config import (
    HumanConfig,
    HumanPreset,
    rand,
    rand_range,
    rand_int_range,
    sleep_ms,
    resolve_config,
    merge_config,
)
from hydra.browser.human.mouse import (
    RawMouse,
    Point,
    human_move,
    human_click,
    human_idle,
    click_target,
)
from hydra.browser.human.keyboard import (
    RawKeyboard,
    human_type,
    SHIFT_SYMBOLS,
    NEARBY_KEYS,
)
from hydra.browser.human.scroll import (
    human_scroll_into_view,
    scroll_to_element,
)
from hydra.browser.human.config import async_sleep_ms
from hydra.browser.human.mouse_async import (
    AsyncRawMouse,
    async_human_move,
    async_human_click,
    async_human_idle,
)
from hydra.browser.human.keyboard_async import (
    AsyncRawKeyboard,
    async_human_type,
)
from hydra.browser.human.scroll_async import (
    async_human_scroll_into_view,
    async_scroll_to_element,
)

__all__ = [
    "HumanConfig",
    "HumanPreset",
    "rand", "rand_range", "rand_int_range", "sleep_ms", "async_sleep_ms",
    "resolve_config", "merge_config",
    # sync
    "RawMouse", "Point",
    "human_move", "human_click", "human_idle", "click_target",
    "RawKeyboard",
    "human_type",
    "SHIFT_SYMBOLS", "NEARBY_KEYS",
    "human_scroll_into_view", "scroll_to_element",
    # async
    "AsyncRawMouse",
    "async_human_move", "async_human_click", "async_human_idle",
    "AsyncRawKeyboard",
    "async_human_type",
    "async_human_scroll_into_view", "async_scroll_to_element",
]
