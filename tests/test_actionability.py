"""Phase 1.5.3 — actionability 검증.

핵심: ensure_actionable 의 retry/backoff 가 일시적 실패에 견디고,
영구적 실패엔 명시적 예외를 던지는지.
"""
from typing import Any, Optional
import pytest

from hydra.browser.human import (
    ActionabilityError,
    ElementNotAttachedError,
    ElementNotVisibleError,
    CHECKS_CLICK,
    CHECKS_INPUT,
    ensure_actionable,
)


class _FakeLocator:
    """Playwright Locator 흉내. count + bounding_box + evaluate 시뮬레이션."""
    def __init__(
        self,
        attached: bool = True,
        visible: bool = True,
        enabled: bool = True,
        editable: bool = True,
        box: Optional[dict] = None,
        boxes_sequence: Optional[list] = None,
    ):
        self._attached = attached
        self._visible = visible
        self._enabled = enabled
        self._editable = editable
        self._box = box or {"x": 100, "y": 100, "width": 80, "height": 30}
        # boxes_sequence: 호출마다 다른 box 반환 (stable 검증용)
        self._boxes_sequence = list(boxes_sequence) if boxes_sequence else None
        self._box_call = 0

    def count(self):
        return 1 if self._attached else 0

    def first(self):
        return self

    @property
    def first(self):
        return self

    def bounding_box(self, timeout: float = 0):
        if self._boxes_sequence and self._box_call < len(self._boxes_sequence):
            b = self._boxes_sequence[self._box_call]
            self._box_call += 1
            return b
        return self._box if self._visible else None

    def evaluate(self, script: str):
        # actionability.py가 evaluate로 disabled/editable 확인
        if "disabled" in script:
            return not self._enabled
        if "editable" in script or "contentEditable" in script:
            return self._editable
        return None

    def is_visible(self):
        return self._visible

    def wait_for(self, state: str = "attached", timeout: float = 0):
        if state == "attached" and not self._attached:
            raise TimeoutError("not attached")
        if state == "visible" and not self._visible:
            raise TimeoutError("not visible")


class _FakePage:
    """Playwright Page 흉내. locator(selector) → _FakeLocator."""
    def __init__(self, loc: "_FakeLocator"):
        self._loc = loc

    def locator(self, selector: str):
        return self._loc


def test_attached_element_passes_attached_check():
    loc = _FakeLocator(attached=True, visible=True, enabled=True)
    page = _FakePage(loc)
    # ensure_actionable signature: (page, selector, checks, timeout, force)
    # Returns None on success, raises on failure.
    ensure_actionable(page, "fake-selector",
                      checks=frozenset({"attached"}), timeout=1000)


def test_not_attached_raises():
    loc = _FakeLocator(attached=False)
    page = _FakePage(loc)
    with pytest.raises(ActionabilityError):
        ensure_actionable(page, "fake-selector",
                          checks=frozenset({"attached"}), timeout=500)


def test_invisible_raises_when_visible_required():
    loc = _FakeLocator(attached=True, visible=False)
    page = _FakePage(loc)
    with pytest.raises(ActionabilityError):
        ensure_actionable(page, "fake-selector",
                          checks=frozenset({"attached", "visible"}), timeout=500)


def test_checks_click_includes_required_states():
    """CHECKS_CLICK 이 클릭에 필요한 모든 검사를 포함."""
    assert "attached" in CHECKS_CLICK
    assert "visible" in CHECKS_CLICK
    assert "enabled" in CHECKS_CLICK
    assert "pointer_events" in CHECKS_CLICK


def test_checks_input_includes_editable():
    """CHECKS_INPUT 은 editable 검사를 포함."""
    assert "editable" in CHECKS_INPUT
    assert "visible" in CHECKS_INPUT


def test_exception_hierarchy():
    """모든 세부 예외가 ActionabilityError 의 자식."""
    assert issubclass(ElementNotAttachedError, ActionabilityError)
    assert issubclass(ElementNotVisibleError, ActionabilityError)
    assert issubclass(ActionabilityError, RuntimeError)
