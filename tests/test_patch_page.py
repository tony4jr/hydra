"""Phase 1.5.4 — patch_page + CDP Isolated World 검증.

실제 Playwright 호출 없이 mock으로 patch_page 의 본질 동작 확인:
- page 메소드 (click/type/scroll_into_view_if_needed/fill 등) 가 가로채짐
- patch 호출 후에도 page 인스턴스 유효
- async 버전 동등
"""
from unittest.mock import MagicMock
import pytest

from hydra.browser.human import (
    HumanConfig, resolve_config,
    patch_page, patch_page_async,
)
from hydra.browser.human import _CursorState


def test_patch_page_callable():
    """patch_page 가 callable."""
    assert callable(patch_page)
    assert callable(patch_page_async)


def test_cursor_state_default_init():
    cur = _CursorState()
    assert cur.x == 0
    assert cur.y == 0


def test_cursor_state_can_set():
    cur = _CursorState()
    cur.x = 100.5
    cur.y = 200.0
    assert cur.x == 100.5


def test_patch_page_replaces_methods():
    """patch_page 호출 후 page method 가 다른 callable 로 교체됨."""
    page = MagicMock()
    # Playwright Locator method 가 존재해야 함
    page.locator = MagicMock(return_value=MagicMock())
    page.context = MagicMock()
    page.context.new_cdp_session = MagicMock(side_effect=Exception("no CDP in mock"))
    page.viewport_size = {"width": 1920, "height": 947}

    # 원본 메소드 참조 보관
    orig_click = page.click
    orig_type = page.type
    orig_fill = page.fill

    cfg = resolve_config("default")
    cur = _CursorState()
    patch_page(page, cfg, cur)

    # 메소드 교체 검증 — patch 후 다른 함수
    assert page.click is not orig_click
    assert page.type is not orig_type
    assert page.fill is not orig_fill


def test_patch_page_async_replaces_methods():
    """async 버전 동일 동작."""
    page = MagicMock()
    page.locator = MagicMock(return_value=MagicMock())
    page.context = MagicMock()
    page.context.new_cdp_session = MagicMock(side_effect=Exception("no CDP"))
    page.viewport_size = {"width": 1920, "height": 947}

    orig_click = page.click
    cfg = resolve_config("default")
    cur = _CursorState()
    patch_page_async(page, cfg, cur)

    assert page.click is not orig_click


def test_resolve_config_default_preset_used_by_patch():
    """patch_page 가 사용하는 cfg 의 핵심 값 검증."""
    cfg = resolve_config("default")
    assert cfg.mouse_min_steps >= 1
    assert cfg.typing_delay > 0
    assert 0 < cfg.mistype_chance < 0.5


def test_isolated_world_class_import():
    """CDP Isolated World 클래스 존재 확인."""
    from hydra.browser.human import _SyncIsolatedWorld, _AsyncIsolatedWorld
    page = MagicMock()
    sync_iw = _SyncIsolatedWorld(page)
    async_iw = _AsyncIsolatedWorld(page)
    assert sync_iw is not None
    assert async_iw is not None
