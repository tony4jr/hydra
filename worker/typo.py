"""간헐적 오타 + 수정 시뮬레이션."""
import random
import asyncio

# 인접 키맵 (한글 키보드 기준)
ADJACENT_KEYS = {
    'ㅂ': 'ㅈ', 'ㅈ': 'ㅂㄷ', 'ㄷ': 'ㅈㄱ', 'ㄱ': 'ㄷㅅ',
    'ㅅ': 'ㄱㅛ', 'ㅛ': 'ㅅㅕ', 'ㅕ': 'ㅛㅑ', 'ㅑ': 'ㅕㅐ',
    'ㅐ': 'ㅑㅔ', 'ㅔ': 'ㅐ',
    'ㅁ': 'ㄴ', 'ㄴ': 'ㅁㅇ', 'ㅇ': 'ㄴㄹ', 'ㄹ': 'ㅇㅎ',
    'ㅎ': 'ㄹㅗ', 'ㅗ': 'ㅎㅓ', 'ㅓ': 'ㅗㅏ', 'ㅏ': 'ㅓㅣ',
    'ㅣ': 'ㅏ',
}


def should_make_typo(probability: float = 0.12) -> bool:
    """오타를 낼지 결정. 기본 12% 확률."""
    return random.random() < probability


async def type_with_occasional_typo(page, selector: str, text: str):
    """가끔 오타를 내고 수정하며 타이핑."""
    element = page.locator(selector).first
    await element.click()
    await asyncio.sleep(random.uniform(0.3, 0.8))

    chars = list(text)
    i = 0
    while i < len(chars):
        char = chars[i]

        if should_make_typo() and i < len(chars) - 1:
            # 오타 입력
            await page.keyboard.type(char + "x", delay=random.randint(80, 200))
            await asyncio.sleep(random.uniform(0.3, 0.8))
            # 잠시 후 발견
            await asyncio.sleep(random.uniform(0.5, 1.5))
            # 백스페이스로 수정
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            # 올바른 다음 글자 입력
            i += 1
            if i < len(chars):
                await page.keyboard.type(chars[i], delay=random.randint(80, 200))
        else:
            # 정상 타이핑
            await page.keyboard.type(char, delay=random.randint(50, 200))

        i += 1
        # 가끔 멈추기 (생각하는 것처럼)
        if random.random() < 0.05:
            await asyncio.sleep(random.uniform(1.0, 3.0))
