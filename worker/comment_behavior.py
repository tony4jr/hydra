"""댓글 작성 전 자연스러운 읽기 행동."""
import random
from hydra.browser.actions import random_delay, scroll_page


async def read_comments_before_posting(page):
    """댓글 작성 전 기존 댓글 읽기 (사람처럼)."""
    comments = page.locator("ytd-comment-thread-renderer")
    count = await comments.count()
    if count == 0:
        return

    # 2~5개 댓글 읽기
    read_count = random.randint(2, min(5, count))
    for i in range(read_count):
        try:
            comment = comments.nth(i)
            # 댓글로 스크롤
            await comment.scroll_into_view_if_needed()
            # 읽는 시간 (댓글 길이에 따라)
            text = await comment.locator("#content-text").inner_text()
            read_time = max(1.5, min(len(text) * 0.05, 5.0))  # 글자 수 기반
            read_time += random.uniform(-0.5, 1.0)
            await random_delay(read_time, read_time + 1.0)
        except Exception:
            continue

    # 가끔 스크롤 올려서 다시 보기
    if random.random() < 0.2:
        await scroll_page(page, scrolls=1, direction="up")
        await random_delay(1.0, 2.0)
