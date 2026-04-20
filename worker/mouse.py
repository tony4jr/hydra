"""마우스 궤적 시뮬레이션 — 자연스러운 곡선 이동."""
import random
import asyncio


def generate_curve_points(start, end, num_points=20):
    """베지어 곡선 기반 자연스러운 마우스 궤적."""
    sx, sy = start
    ex, ey = end
    mid_x = (sx + ex) / 2 + random.randint(-100, 100)
    mid_y = (sy + ey) / 2 + random.randint(-50, 50)
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * mid_x + t**2 * ex
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * mid_y + t**2 * ey
        x += random.randint(-2, 2)
        y += random.randint(-2, 2)
        points.append((int(x), int(y)))
    return points


async def move_mouse_naturally(page, target_x, target_y):
    start_x = random.randint(100, 800)
    start_y = random.randint(100, 600)
    points = generate_curve_points(
        (start_x, start_y), (target_x, target_y), num_points=random.randint(15, 30)
    )
    for x, y in points:
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.002, 0.008))


async def click_with_mouse_move(page, selector):
    element = page.locator(selector).first
    await human_click(element)


async def human_click(locator, timeout: int = 10_000) -> None:
    """사람처럼 element 를 클릭.

    - bounding box 안의 "중심 근방 (20~80%)" 랜덤 위치 선택 (정중앙 회피)
    - 베지어 곡선 마우스 경로로 이동 (봇 특유의 직선 이동 회피)
    - 클릭 직전 짧은 랜덤 pause

    box 를 못 구하면 (디태치된 요소, shadow DOM 일부 등) 기본 `.click()` 폴백.
    """
    try:
        await locator.wait_for(state="visible", timeout=timeout)
    except Exception:
        pass

    box = None
    try:
        box = await locator.bounding_box()
    except Exception:
        box = None

    if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
        # 폴백 — Playwright 기본 클릭 (element 자체가 타겟)
        await locator.click(timeout=timeout)
        return

    page = None
    try:
        page = locator.page  # Playwright Locator 은 .page 속성 보유
    except Exception:
        pass

    # 정중앙 회피 — 20~80% 내 랜덤
    rx = random.uniform(0.2, 0.8)
    ry = random.uniform(0.2, 0.8)
    target_x = box["x"] + rx * box["width"]
    target_y = box["y"] + ry * box["height"]

    if page is None:
        # 폴백 — 기본 클릭
        await locator.click(timeout=timeout)
        return

    await move_mouse_naturally(page, target_x, target_y)
    await asyncio.sleep(random.uniform(0.04, 0.18))
    await page.mouse.click(target_x, target_y)
