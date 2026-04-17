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
    box = await element.bounding_box()
    if not box:
        await element.click()
        return
    target_x = int(box["x"] + random.uniform(5, box["width"] - 5))
    target_y = int(box["y"] + random.uniform(3, box["height"] - 3))
    await move_mouse_naturally(page, target_x, target_y)
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(target_x, target_y)
