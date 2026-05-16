"""hydra.browser.human — 인간 행동 시뮬레이션 레이어.

Origin: CloakBrowser (https://github.com/CloakHQ/CloakBrowser) MIT licensed.
포팅 범위: human/ 모듈만. binary/geoip/examples는 제외 (AdsPower와 중복 또는 무관).

Phase 1.5 — config/mouse/keyboard/scroll 4 sync + 3 async + actionability.
patch_page wiring 은 Phase 1.5.4.
"""
from hydra.browser.human.config import (
    HumanConfig,
    HumanPreset,
    rand,
    rand_range,
    rand_int_range,
    sleep_ms,
    async_sleep_ms,
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
from hydra.browser.human.actionability import (
    ensure_actionable,
    ensure_stable,
    check_pointer_events,
    ensure_actionable_handle,
    check_pointer_events_handle,
    ActionabilityError,
    ElementNotAttachedError,
    ElementNotVisibleError,
    ElementNotStableError,
    ElementNotEnabledError,
    ElementNotEditableError,
    ElementNotReceivingEventsError,
    CHECKS_CLICK,
    CHECKS_HOVER,
    CHECKS_INPUT,
    CHECKS_FOCUS,
    CHECKS_CHECK,
)
from hydra.browser.human.actionability_async import (
    async_ensure_actionable,
    async_ensure_stable,
    async_check_pointer_events,
    async_ensure_actionable_handle,
    async_check_pointer_events_handle,
)

__all__ = [
    # config
    "HumanConfig", "HumanPreset",
    "rand", "rand_range", "rand_int_range", "sleep_ms", "async_sleep_ms",
    "resolve_config", "merge_config",
    # sync mouse/keyboard/scroll
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
    # actionability
    "ensure_actionable", "ensure_stable", "check_pointer_events",
    "ensure_actionable_handle", "check_pointer_events_handle",
    "ActionabilityError",
    "ElementNotAttachedError", "ElementNotVisibleError",
    "ElementNotStableError", "ElementNotEnabledError",
    "ElementNotEditableError", "ElementNotReceivingEventsError",
    "CHECKS_CLICK", "CHECKS_HOVER", "CHECKS_INPUT",
    "CHECKS_FOCUS", "CHECKS_CHECK",
    "async_ensure_actionable", "async_ensure_stable",
    "async_check_pointer_events",
    "async_ensure_actionable_handle", "async_check_pointer_events_handle",
]
