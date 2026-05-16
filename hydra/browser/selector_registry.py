"""Phase 2.2 — Selector Registry.

raw CSS/XPath 가 worker/login.py, hydra/browser/actions.py 등 곳곳에 산재되어
YouTube/Google UI 변경 시 grep-and-replace 부담. 한 곳으로 통합하면:
  - selector 1 곳에서 수정 → 워커 self-update 한 번
  - 다중 fallback (primary → backup1 → backup2) 표준화
  - admin UI 에 "현재 사용 중인 selector 목록" 노출 가능 (Phase 3)

호출 패턴:
  from hydra.browser.selector_registry import SR
  await page.locator(SR.get_first("login_email_input")).fill(email)

  # 다중 fallback 시도
  for sel in SR.candidates("yt_comment_thread"):
      loc = page.locator(sel)
      if await loc.count() > 0:
          break
"""
from __future__ import annotations

from typing import Iterable


class SelectorRegistry:
    """단순 dict wrapper — 추후 yaml/db 로딩으로 확장 가능.

    값은 단일 selector 문자열 또는 list (fallback chain).
    """

    def __init__(self):
        # 분류 prefix: login_*, yt_* (YouTube), gh_* (Google general)
        self._reg: dict[str, str | list[str]] = {
            # ── Google login ────────────────────────────────────────────
            "login_email_input": "input[type='email']",
            "login_password_input": "input[type='password']:visible",
            "login_identifier_next": [
                "#identifierNext button",
                "button:has-text('다음')",
                "button:has-text('Next')",
            ],
            "login_password_next": [
                "#passwordNext button",
                "button:has-text('다음')",
                "button:has-text('Next')",
            ],
            "login_account_chooser_by_email": [
                "div[data-email='{email}']",
                "li[data-email='{email}']",
                "div:has-text('{email}')",
            ],
            # post-login skip 버튼 — locale 무관 텍스트는 별도 SKIP_ARIA_PATTERNS 가 있어서
            # 여기는 selector 기준만.
            "login_skip_button_generic": [
                "button[jsname]:has-text('나중에')",
                "button:has-text('Skip')",
                "button:has-text('Not now')",
            ],
            # ── YouTube ─────────────────────────────────────────────────
            "yt_avatar_button": "button#avatar-btn, img.yt-spec-avatar-shape__image",
            # 실제 운영 코드(hydra/browser/actions.py:255-290) 와 정합:
            # ytd-comment-simplebox-renderer 안에서만 동작 — reply box (ytd-comment-replies-renderer)
            # 와 ID 가 중복되므로 root scope 가 simplebox-renderer 여야 함.
            "yt_comment_simplebox_root": "ytd-comment-simplebox-renderer",
            "yt_comment_placeholder": "#simplebox-placeholder, #placeholder-area",
            "yt_comment_input": "#contenteditable-root",
            "yt_comment_submit_button": "ytd-button-renderer#submit-button button:not([disabled])",
            "yt_comment_thread_by_id": [
                # comment-id, data-cid, data-comment-id, lc=ID URL — 6단 OR (기존 패턴 보존)
                "ytd-comment-thread-renderer[comment-id='{cid}']",
                "ytd-comment-thread-renderer[data-cid='{cid}']",
                "ytd-comment-thread-renderer[data-comment-id='{cid}']",
                "ytd-comment-thread-renderer:has([data-cid='{cid}'])",
                "ytd-comment-thread-renderer:has([data-comment-id='{cid}'])",
                "ytd-comment-thread-renderer:has(a[href*='lc={cid}'])",
            ],
            "yt_video_search_link": "ytd-video-renderer a#video-title, ytd-video-renderer a#thumbnail",
            # ── Google general (security, trust device, etc.) ───────────
            "google_trust_device_skip": [
                "button:has-text('나중에')",
                "button:has-text('Maybe later')",
                "button[jsname][data-action='not_now']",
            ],
        }

    def get_first(self, key: str, **fmt: str) -> str:
        """primary selector 1 개 반환 (list 면 첫 항목). {placeholder} 치환."""
        v = self._reg[key]
        sel = v[0] if isinstance(v, list) else v
        return sel.format(**fmt) if fmt else sel

    def candidates(self, key: str, **fmt: str) -> list[str]:
        """fallback chain 전체. 항상 list."""
        v = self._reg[key]
        sels = v if isinstance(v, list) else [v]
        if fmt:
            return [s.format(**fmt) for s in sels]
        return list(sels)

    def keys(self) -> Iterable[str]:
        return self._reg.keys()

    def register(self, key: str, value: str | list[str]) -> None:
        """런타임에 selector 추가/교체 (테스트 또는 hot patch)."""
        self._reg[key] = value


# 모듈 레벨 singleton
SR = SelectorRegistry()
