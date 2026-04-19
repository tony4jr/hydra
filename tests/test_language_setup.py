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

        # delete_other_languages: has_target probe → 삭제할 게 없음 (False)
        if "btns.some" in script and "삭제" in script:
            return False
        # delete_other_languages: click target probe → 못 찾음
        if "btns.find" in script and "/삭제" in script:
            return None

        if "/edit|chỉnh" in script:
            # primary edit button click (main flow)
            return True

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
    # 한 번만 /language 방문, 편집 플로우는 안 탐
    assert page.goto_calls == [language_setup.LANGUAGE_URL]
    # initial lang + delete-other-languages probe (둘 다 짧게 끝남)
    assert len(page.eval_calls) <= 3


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
        # edit 버튼 탐지/클릭 스크립트는 단독 (delete 쪽 aria-label 체크는 문자열 다름)
        if "/edit|chỉnh" in script:
            return False
        return await original_eval(script, *args)

    page.evaluate = broken_eval

    result = await language_setup.ensure_korean_language(page)
    assert result is False


@pytest.mark.asyncio
async def test_delete_other_languages_loops_and_exits(monkeypatch):
    """'기타 언어' 항목 2개를 순차 삭제 후 루프 종료."""
    from worker import language_setup

    async def no_delay(*a, **k): pass
    monkeypatch.setattr(language_setup, "random_delay", no_delay)

    # 2번째 호출까지 True (삭제할 게 있음), 3번째 이후 False (없음)
    has_target_sequence = [True, True, False]
    click_sequence = ["Tiếng Việt(베트남어) 삭제", "日本語 삭제"]
    confirm_sequence = ["제거", "제거"]

    page = MagicMock()
    page.goto = AsyncMock()
    has_target_iter = iter(has_target_sequence)
    click_iter = iter(click_sequence)
    confirm_iter = iter(confirm_sequence)

    async def fake_eval(script, *args):
        if "btns.some" in script:
            return next(has_target_iter, False)
        if "btns.find" in script and "/삭제" in script:
            return next(click_iter, None)
        if "role=\"dialog\"" in script or "role='dialog'" in script or "alertdialog" in script:
            return next(confirm_iter, False)
        return None

    page.evaluate = fake_eval
    removed = await language_setup._delete_other_languages(page, timeout_ms=5_000)
    assert removed == 2
