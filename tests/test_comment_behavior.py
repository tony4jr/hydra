"""댓글 전 읽기 행동 테스트."""
from worker.comment_behavior import read_comments_before_posting


def test_read_comments_before_posting_is_async():
    """read_comments_before_posting이 코루틴 함수인지 확인."""
    import asyncio
    assert asyncio.iscoroutinefunction(read_comments_before_posting)


def test_import_comment_behavior():
    """모듈 임포트 정상 확인."""
    from worker import comment_behavior
    assert hasattr(comment_behavior, "read_comments_before_posting")
