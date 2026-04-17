"""간헐적 오타+수정 시뮬레이션 테스트."""
from worker.typo import should_make_typo, type_with_occasional_typo, ADJACENT_KEYS


def test_should_make_typo_always_true():
    """probability=1.0이면 항상 True."""
    assert should_make_typo(1.0) is True


def test_should_make_typo_always_false():
    """probability=0.0이면 항상 False."""
    assert should_make_typo(0.0) is False


def test_should_make_typo_default():
    """기본 확률(0.12)로 호출 가능."""
    result = should_make_typo()
    assert isinstance(result, bool)


def test_adjacent_keys_not_empty():
    """인접 키맵이 비어있지 않아야 함."""
    assert len(ADJACENT_KEYS) > 0


def test_type_with_occasional_typo_is_async():
    """type_with_occasional_typo가 코루틴 함수인지 확인."""
    import asyncio
    assert asyncio.iscoroutinefunction(type_with_occasional_typo)
