"""언어 설정 워밍업 서브스텝 단위 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock


class FakePage:
    """ensure_korean_language 가 사용하는 Page 표면만 모사."""

    def __init__(self, initial_lang="vi", final_lang="ko-KR",
                 eval_responses=None):
        self._lang = initial_lang
        self._final_lang = final_lang
        self._save_eval_sequence = []
        self._eval_responses = eval_responses or {}
        self.goto_calls = []
        self.eval_calls = []

    async def goto(self, url, **_):
        self.goto_calls.append(url)

    async def evaluate(self, script, *args):
        self.eval_calls.append(script)

        if "document.documentElement.lang" in script and "===" not in script:
            # _current_lang
            return self._lang

        if "b.getAttribute('aria-label')" in script:
            # edit button click
            return True

        if "TARGET_LANG_NAME" in script or "'한국어'" in script:
            # Wrong branch — the script interpolates
            pass

        if "o.textContent.trim() === '한국어'" in script:
            return True

        if "o.textContent.trim() === '대한민국'" in script:
            return True

        if "save.click" in script:
            # simulate save being enabled & clicked, then language updates
            self._lang = self._final_lang
            return "clicked"

        return False

    def locator(self, selector):
        loc = MagicMock()
        loc.wait_for = AsyncMock()
        return loc


@pytest.mark.asyncio
async def test_ensure_korean_language_skips_when_already_ko(monkeypatch):
    from worker import language_setup

    page = FakePage(initial_lang="ko-KR", final_lang="ko-KR")

    async def no_delay(*a, **k): pass
    monkeypatch.setattr(language_setup, "random_delay", no_delay)

    result = await language_setup.ensure_korean_language(page)
    assert result is True
    # only /language navigate + initial lang check — no edit workflow evaluations
    assert page.goto_calls == [language_setup.LANGUAGE_URL]
    assert len(page.eval_calls) == 1  # the initial current_lang probe


@pytest.mark.asyncio
async def test_ensure_korean_language_switches_from_vi_to_ko(monkeypatch):
    from worker import language_setup

    page = FakePage(initial_lang="vi", final_lang="ko-KR")

    async def no_delay(*a, **k): pass
    async def no_type(*a, **k): pass
    monkeypatch.setattr(language_setup, "random_delay", no_delay)
    monkeypatch.setattr(language_setup, "type_human", no_type)

    result = await language_setup.ensure_korean_language(page)
    assert result is True
    # verify we went through the full flow
    assert page.goto_calls[0] == language_setup.LANGUAGE_URL
    # final lang should be updated
    assert page._lang.startswith("ko")


@pytest.mark.asyncio
async def test_ensure_korean_language_fails_when_edit_button_missing(monkeypatch):
    from worker import language_setup

    page = FakePage(initial_lang="vi")

    async def no_delay(*a, **k): pass
    monkeypatch.setattr(language_setup, "random_delay", no_delay)

    original_eval = page.evaluate

    async def broken_eval(script, *args):
        if "b.getAttribute('aria-label')" in script:
            return False
        return await original_eval(script, *args)

    page.evaluate = broken_eval

    result = await language_setup.ensure_korean_language(page)
    assert result is False
