# HYDRA v2 브라우저 자동화 엔진 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Worker executor의 스텁을 실제 브라우저 자동화로 교체하여, 워밍업 모드를 실행 가능하게 만든다.

**Architecture:** 기존 hydra/browser/ 코드(actions, driver, adspower)를 Worker에서 임포트하여 사용. 신규 worker/session.py가 세션 관리(프로필 열기/닫기/태스크 루프)를 담당. executor.py의 스텁 핸들러를 실제 브라우저 동작으로 교체.

**Tech Stack:** Playwright (CDP), AdsPower Local API, pyotp, httpx

**Spec Reference:** `docs/superpowers/specs/2026-04-17-browser-automation-design.md`

---

## File Structure

```
worker/
├── executor.py           # MODIFY: 스텁 → 실제 브라우저 자동화 연결
├── session.py            # CREATE: 브라우저 세션 관리 (열기/닫기/태스크 루프)
├── warmup.py             # CREATE: 워밍업 전용 로직
├── login.py              # CREATE: 자동 로그인 + 2FA
├── google_activity.py    # CREATE: Gmail/Google 검색 행동
├── mouse.py              # CREATE: 마우스 궤적 시뮬레이션
├── app.py                # MODIFY: 세션 기반 실행으로 전환
hydra/
├── browser/actions.py    # MODIFY: 숏츠 패턴 + 댓글 읽기 + 오타 추가
├── db/models.py          # MODIFY: Worker에 allow_preparation/allow_campaign 추가
tests/
├── test_session.py       # CREATE
├── test_warmup.py        # CREATE
├── test_login.py         # CREATE
├── test_mouse.py         # CREATE
```

---

### Task 1: Worker 세션 관리 (session.py)

**Files:**
- Create: `worker/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: session.py 작성**

```python
"""브라우저 세션 관리 — 프로필 열기/닫기/태스크 루프."""
import asyncio
import json
import random
from datetime import datetime, UTC
from hydra.browser.driver import BrowserSession
from hydra.browser.actions import random_delay
from hydra.infra.ip import rotate_ip
from worker.config import config

class WorkerSession:
    """한 계정의 브라우저 세션. 여러 태스크를 자연스럽게 실행."""

    def __init__(self, profile_id: str, account_id: int, device_id: str | None = None):
        self.profile_id = profile_id
        self.account_id = account_id
        self.device_id = device_id
        self.browser: BrowserSession | None = None
        self.tasks_completed = 0
        self.max_tasks_per_session = random.randint(3, 8)
        self.max_session_minutes = random.randint(20, 45)
        self.started_at: datetime | None = None

    async def start(self) -> bool:
        """세션 시작: IP 변경 → 프로필 열기 → YouTube 접속."""
        try:
            # IP 변경
            if self.device_id:
                await rotate_ip(self.device_id)

            # AdsPower 프로필 열기 + Playwright CDP 연결
            self.browser = BrowserSession(self.profile_id)
            await self.browser.start()

            # YouTube 접속
            await self.browser.goto("https://www.youtube.com")
            await random_delay(2.0, 4.0)

            self.started_at = datetime.now(UTC)
            return True
        except Exception as e:
            print(f"[Session] Failed to start: {e}")
            await self.close()
            return False

    async def should_continue(self) -> bool:
        """세션 계속 여부 판단."""
        if not self.started_at:
            return False
        elapsed = (datetime.now(UTC) - self.started_at).total_seconds() / 60
        if elapsed >= self.max_session_minutes:
            return False
        if self.tasks_completed >= self.max_tasks_per_session:
            return False
        return True

    async def do_natural_browsing(self):
        """태스크 사이에 자연스러운 브라우징."""
        if not self.browser:
            return
        page = self.browser.page

        action = random.choices(
            ["shorts", "watch_recommended", "scroll_home", "nothing"],
            weights=[30, 25, 25, 20],
        )[0]

        if action == "shorts":
            await self._browse_shorts(page)
        elif action == "watch_recommended":
            await self._watch_recommended(page)
        elif action == "scroll_home":
            from hydra.browser.actions import scroll_page
            await self.browser.goto("https://www.youtube.com")
            await scroll_page(page, scrolls=random.randint(2, 5))
        # nothing = 그냥 대기
        await random_delay(2.0, 5.0)

    async def _browse_shorts(self, page):
        """숏츠 시청 (자연스러운 패턴)."""
        await self.browser.goto("https://www.youtube.com/shorts")
        await random_delay(1.5, 3.0)

        num_shorts = random.randint(2, 15)
        for _ in range(num_shorts):
            # 시청 패턴
            behavior = random.choices(
                ["skip", "short_watch", "full_watch", "rewatch"],
                weights=[40, 30, 20, 5],
            )[0]

            if behavior == "skip":
                await random_delay(1.0, 2.0)
            elif behavior == "short_watch":
                await random_delay(3.0, 10.0)
            elif behavior == "full_watch":
                await random_delay(15.0, 60.0)
            elif behavior == "rewatch":
                await random_delay(15.0, 40.0)
                continue  # 다시 보기 — 스와이프 안 함

            # 가끔 좋아요
            if random.random() < 0.1:
                from hydra.browser.actions import click_like_button
                await click_like_button(page, target="video")

            # 다음 숏츠로 스와이프
            await page.keyboard.press("ArrowDown")
            await random_delay(0.3, 1.0)

    async def _watch_recommended(self, page):
        """추천 영상 하나 시청."""
        from hydra.browser.actions import watch_video, handle_ad
        await self.browser.goto("https://www.youtube.com")
        await random_delay(1.5, 3.0)

        # 추천 영상 클릭
        thumbnails = page.locator("ytd-rich-item-renderer a#thumbnail")
        count = await thumbnails.count()
        if count > 0:
            idx = random.randint(0, min(count - 1, 9))
            await thumbnails.nth(idx).click()
            await random_delay(2.0, 4.0)
            await handle_ad(page)

            # 시청 (최대 3분)
            duration = random.randint(10, 180)
            await watch_video(page, duration)

    async def close(self):
        """세션 종료: 브라우저 닫기."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.close()
```

- [ ] **Step 2: 테스트 작성 (tests/test_session.py)**

```python
from worker.session import WorkerSession

def test_session_init():
    session = WorkerSession("profile_123", account_id=1, device_id="device1")
    assert session.profile_id == "profile_123"
    assert session.account_id == 1
    assert session.tasks_completed == 0
    assert 3 <= session.max_tasks_per_session <= 8
    assert 20 <= session.max_session_minutes <= 45

def test_session_should_continue_no_start():
    session = WorkerSession("profile_123", account_id=1)
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(session.should_continue())
    assert result is False

def test_session_max_tasks():
    session = WorkerSession("profile_123", account_id=1)
    session.started_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
    session.max_tasks_per_session = 3
    session.tasks_completed = 3
    import asyncio
    result = asyncio.get_event_loop().run_until_complete(session.should_continue())
    assert result is False
```

- [ ] **Step 3: 테스트 실행**

Run: `.venv/bin/python -m pytest tests/test_session.py -v`
Expected: 3 PASSED

- [ ] **Step 4: Commit**

```bash
git add worker/session.py tests/test_session.py
git commit -m "feat: Worker 세션 관리 (프로필 열기/닫기/자연 브라우징)"
```

---

### Task 2: 마우스 궤적 시뮬레이션 (mouse.py)

**Files:**
- Create: `worker/mouse.py`
- Create: `tests/test_mouse.py`

- [ ] **Step 1: mouse.py 작성**

```python
"""마우스 궤적 시뮬레이션 — 자연스러운 곡선 이동."""
import random
import math

def generate_curve_points(
    start: tuple[int, int],
    end: tuple[int, int],
    num_points: int = 20,
) -> list[tuple[int, int]]:
    """시작점에서 끝점까지 자연스러운 곡선 궤적 생성.
    
    베지어 곡선 기반으로 약간의 랜덤 오프셋을 추가.
    """
    sx, sy = start
    ex, ey = end

    # 랜덤 제어점 (곡선을 만듦)
    mid_x = (sx + ex) / 2 + random.randint(-100, 100)
    mid_y = (sy + ey) / 2 + random.randint(-50, 50)

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # 2차 베지어 곡선
        x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * mid_x + t ** 2 * ex
        y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * mid_y + t ** 2 * ey
        # 약간의 떨림 추가
        x += random.randint(-2, 2)
        y += random.randint(-2, 2)
        points.append((int(x), int(y)))

    return points

async def move_mouse_naturally(page, target_x: int, target_y: int):
    """마우스를 목표 지점으로 자연스럽게 이동."""
    # 현재 마우스 위치 (알 수 없으면 랜덤 시작)
    start_x = random.randint(100, 800)
    start_y = random.randint(100, 600)

    points = generate_curve_points(
        (start_x, start_y),
        (target_x, target_y),
        num_points=random.randint(15, 30),
    )

    for x, y in points:
        await page.mouse.move(x, y)
        # 이동 속도 랜덤 (2~8ms per step)
        import asyncio
        await asyncio.sleep(random.uniform(0.002, 0.008))

async def click_with_mouse_move(page, selector: str):
    """요소 위치로 마우스 이동 후 클릭."""
    element = page.locator(selector).first
    box = await element.bounding_box()
    if not box:
        await element.click()
        return

    # 요소 내 랜덤 위치
    target_x = int(box["x"] + random.uniform(5, box["width"] - 5))
    target_y = int(box["y"] + random.uniform(3, box["height"] - 3))

    await move_mouse_naturally(page, target_x, target_y)

    # 클릭 전 짧은 대기
    import asyncio
    await asyncio.sleep(random.uniform(0.05, 0.15))
    await page.mouse.click(target_x, target_y)
```

- [ ] **Step 2: 테스트 작성**

```python
from worker.mouse import generate_curve_points

def test_generate_curve_points():
    points = generate_curve_points((0, 0), (100, 100), num_points=20)
    assert len(points) == 21
    # 시작점 근처
    assert abs(points[0][0]) < 5
    assert abs(points[0][1]) < 5
    # 끝점 근처
    assert abs(points[-1][0] - 100) < 5
    assert abs(points[-1][1] - 100) < 5

def test_curve_points_randomness():
    p1 = generate_curve_points((0, 0), (100, 100))
    p2 = generate_curve_points((0, 0), (100, 100))
    # 두 번 생성하면 다른 경로
    assert p1 != p2

def test_curve_points_count():
    points = generate_curve_points((0, 0), (500, 300), num_points=10)
    assert len(points) == 11
```

- [ ] **Step 3: 테스트 실행 + Commit**

```bash
.venv/bin/python -m pytest tests/test_mouse.py -v
git add worker/mouse.py tests/test_mouse.py
git commit -m "feat: 마우스 궤적 시뮬레이션 (베지어 곡선)"
```

---

### Task 3: Google 활동 (google_activity.py)

**Files:**
- Create: `worker/google_activity.py`
- Create: `tests/test_google_activity.py`

- [ ] **Step 1: google_activity.py 작성**

```python
"""Gmail 확인 + Google 검색 — 자연스러운 쿠키 축적."""
import random
from hydra.browser.actions import random_delay, type_human, scroll_page

# 페르소나 관심사별 검색어
SEARCH_QUERIES = {
    "대학생": ["과제 마감일", "대학생 할인", "아르바이트 추천", "시험 공부법"],
    "회사원": ["퇴근 후 운동", "점심 맛집", "연차 사용법", "이직 준비"],
    "자영업": ["소상공인 대출", "매출 관리", "가게 인테리어", "배달 앱 수수료"],
    "주부": ["아이 간식 레시피", "육아 꿀팁", "주부 재테크", "집안일 꿀팁"],
    "프리랜서": ["프리랜서 세금", "재택근무 환경", "포트폴리오", "작업 카페"],
    "default": ["오늘 날씨", "맛집 추천", "영화 추천", "뉴스", "운동법"],
}

async def maybe_check_gmail(page, probability: float = 0.3) -> bool:
    """Gmail 확인 (확률 기반)."""
    if random.random() > probability:
        return False

    await page.goto("https://mail.google.com")
    await random_delay(3.0, 6.0)

    # 받은편지함 로딩 대기
    try:
        await page.wait_for_selector("div[role='main']", timeout=10000)
    except Exception:
        return False

    # 이메일 1~2개 열어보기
    emails = page.locator("tr.zA")
    count = await emails.count()
    if count > 0:
        clicks = random.randint(1, min(2, count))
        for _ in range(clicks):
            idx = random.randint(0, min(count - 1, 5))
            await emails.nth(idx).click()
            await random_delay(3.0, 8.0)
            await page.go_back()
            await random_delay(1.0, 3.0)

    await random_delay(2.0, 5.0)
    return True

async def maybe_google_search(page, occupation: str = "default", probability: float = 0.4) -> bool:
    """Google 검색 (확률 기반, 페르소나 관심사)."""
    if random.random() > probability:
        return False

    queries = SEARCH_QUERIES.get(occupation, SEARCH_QUERIES["default"])
    query = random.choice(queries)

    await page.goto("https://www.google.com")
    await random_delay(1.5, 3.0)

    # 검색어 입력
    search_box = page.locator("textarea[name='q'], input[name='q']").first
    await type_human(page, "textarea[name='q'], input[name='q']", query)
    await random_delay(0.5, 1.5)
    await page.keyboard.press("Enter")
    await random_delay(2.0, 4.0)

    # 검색 결과 1~2개 클릭
    results = page.locator("div#search a h3")
    count = await results.count()
    if count > 0:
        clicks = random.randint(1, min(2, count))
        for _ in range(clicks):
            idx = random.randint(0, min(count - 1, 4))
            await results.nth(idx).click()
            await random_delay(5.0, 15.0)
            await page.go_back()
            await random_delay(1.0, 3.0)

    return True
```

- [ ] **Step 2: 테스트 작성**

```python
from worker.google_activity import SEARCH_QUERIES

def test_search_queries_have_default():
    assert "default" in SEARCH_QUERIES
    assert len(SEARCH_QUERIES["default"]) > 0

def test_search_queries_occupations():
    for occupation in ["대학생", "회사원", "자영업", "주부", "프리랜서"]:
        assert occupation in SEARCH_QUERIES
        assert len(SEARCH_QUERIES[occupation]) >= 3

def test_search_queries_all_strings():
    for occupation, queries in SEARCH_QUERIES.items():
        for q in queries:
            assert isinstance(q, str)
            assert len(q) > 0
```

- [ ] **Step 3: 테스트 실행 + Commit**

```bash
.venv/bin/python -m pytest tests/test_google_activity.py -v
git add worker/google_activity.py tests/test_google_activity.py
git commit -m "feat: Google 활동 (Gmail 확인 + 검색 — 쿠키 축적)"
```

---

### Task 4: 자동 로그인 + 2FA (login.py)

**Files:**
- Create: `worker/login.py`
- Create: `tests/test_login.py`

- [ ] **Step 1: login.py 작성**

```python
"""자동 로그인 + 2FA — 계정 준비 단계."""
import pyotp
from hydra.browser.actions import random_delay, type_human

async def check_logged_in(page) -> bool:
    """YouTube 로그인 상태 확인."""
    try:
        avatar = page.locator("button#avatar-btn, img.yt-spec-avatar-shape__image")
        await avatar.wait_for(timeout=5000)
        return True
    except Exception:
        return False

async def auto_login(page, email: str, password: str, totp_secret: str | None = None) -> bool:
    """Google 자동 로그인.
    
    Returns True if login successful, False otherwise.
    """
    try:
        # Google 로그인 페이지
        await page.goto("https://accounts.google.com/signin")
        await random_delay(2.0, 4.0)

        # 이메일 입력
        email_input = page.locator("input[type='email']")
        await email_input.wait_for(timeout=10000)
        await type_human(page, "input[type='email']", email)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(2.0, 4.0)

        # 비밀번호 입력
        password_input = page.locator("input[type='password']")
        await password_input.wait_for(timeout=10000)
        await type_human(page, "input[type='password']", password)
        await random_delay(0.5, 1.5)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)

        # 2FA 확인
        if totp_secret:
            await _handle_2fa(page, totp_secret)

        # 로그인 성공 확인
        await page.wait_for_url("**/myaccount.google.com/**", timeout=15000)
        return True

    except Exception as e:
        print(f"[Login] Failed: {e}")
        return False

async def _handle_2fa(page, totp_secret: str):
    """TOTP 2FA 코드 입력."""
    try:
        totp_input = page.locator("input[name='totpPin'], input#totpPin")
        await totp_input.wait_for(timeout=10000)

        code = pyotp.TOTP(totp_secret).now()
        await type_human(page, "input[name='totpPin'], input#totpPin", code)
        await random_delay(0.5, 1.0)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)
    except Exception:
        pass  # 2FA 안 뜨면 넘어감

async def ensure_logged_in(page, email: str, password: str, totp_secret: str | None = None) -> bool:
    """로그인 상태 확인 → 안 되어 있으면 자동 로그인."""
    if await check_logged_in(page):
        return True
    return await auto_login(page, email, password, totp_secret)
```

- [ ] **Step 2: 테스트 작성**

```python
import pyotp
from worker.login import _handle_2fa

def test_totp_code_generation():
    """TOTP 코드 생성 확인."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert len(code) == 6
    assert code.isdigit()

def test_totp_code_verification():
    """TOTP 코드 검증."""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()
    assert totp.verify(code) is True
    assert totp.verify("000000") is False
```

- [ ] **Step 3: 테스트 실행 + Commit**

```bash
.venv/bin/python -m pytest tests/test_login.py -v
git add worker/login.py tests/test_login.py
git commit -m "feat: 자동 로그인 + 2FA (Google 계정)"
```

---

### Task 5: 워밍업 실행 로직 (warmup.py)

**Files:**
- Create: `worker/warmup.py`
- Create: `tests/test_warmup.py`

- [ ] **Step 1: warmup.py 작성**

```python
"""워밍업 모드 — 2~3일 점진적 활동 증가."""
import random
import json
from datetime import datetime, UTC
from hydra.browser.actions import (
    random_delay, scroll_page, click_like_button,
    post_comment, watch_video, handle_ad, scroll_to_comments,
)
from worker.session import WorkerSession
from worker.google_activity import maybe_check_gmail, maybe_google_search
from worker.login import ensure_logged_in

class WarmupExecutor:
    """워밍업 세션 실행기."""

    def __init__(self, session: WorkerSession, day: int = 1, persona: dict | None = None):
        """
        Args:
            session: 활성 브라우저 세션
            day: 워밍업 일차 (1, 2, 3)
            persona: 페르소나 정보 {"occupation": "회사원", ...}
        """
        self.session = session
        self.day = day
        self.persona = persona or {}
        self.occupation = self.persona.get("occupation", "default")

    async def run(self) -> dict:
        """워밍업 세션 실행. 결과 요약 반환."""
        page = self.session.browser.page
        result = {"day": self.day, "actions": []}

        # Google 활동 (Day 2+)
        if self.day >= 2:
            if await maybe_check_gmail(page, probability=0.3):
                result["actions"].append("gmail_check")
            if await maybe_google_search(page, self.occupation, probability=0.4):
                result["actions"].append("google_search")

            # YouTube로 복귀
            await self.session.browser.goto("https://www.youtube.com")
            await random_delay(2.0, 4.0)

        # 숏츠 시청
        await self.session._browse_shorts(page)
        result["actions"].append("shorts")

        # 영상 시청
        videos_to_watch = self._pick_video_count()
        for _ in range(videos_to_watch):
            await self.session._watch_recommended(page)
            result["actions"].append("watch_video")

            # 좋아요 (확률)
            if random.random() < self._like_probability():
                await click_like_button(page, target="video")
                result["actions"].append("like_video")

        # 댓글 (Day 2+)
        if self.day >= 2:
            comments_to_post = self._pick_comment_count()
            for _ in range(comments_to_post):
                # 추천 영상으로 이동
                await self.session._watch_recommended(page)
                await scroll_to_comments(page)
                await random_delay(3.0, 8.0)  # 댓글 읽기 행동

                # 비프로모 캐주얼 댓글
                comment_text = self._generate_casual_comment()
                comment_id = await post_comment(page, comment_text)
                if comment_id:
                    result["actions"].append(f"comment:{comment_id}")

        # 구독 (Day 2+)
        if self.day >= 2 and random.random() < 0.3:
            subscribe_btn = page.locator("ytd-subscribe-button-renderer button")
            try:
                if await subscribe_btn.count() > 0:
                    await subscribe_btn.first.click()
                    result["actions"].append("subscribe")
            except Exception:
                pass

        return result

    def _pick_video_count(self) -> int:
        if self.day == 1:
            return random.randint(1, 2)
        elif self.day == 2:
            return random.randint(2, 3)
        return random.randint(2, 3)

    def _pick_comment_count(self) -> int:
        if self.day == 1:
            return 0
        elif self.day == 2:
            return random.randint(1, 2)
        return random.randint(3, 5)

    def _like_probability(self) -> float:
        if self.day == 1:
            return 0.3
        return 0.5

    def _generate_casual_comment(self) -> str:
        """워밍업용 캐주얼 댓글 (비프로모)."""
        comments = [
            "좋은 영상이네요~",
            "오 이런 정보 처음 알았어요",
            "유익합니다 감사해요",
            "저도 한번 해봐야겠다",
            "와 진짜 좋은 내용이네요",
            "구독했어요!",
            "잘 봤습니다~",
            "영상 잘 만드시네요",
            "이거 궁금했는데 감사합니다",
            "오늘도 유익한 영상 감사해요",
            "대박 정보 감사합니다ㅋㅋ",
            "ㅋㅋㅋ 재밌다",
            "요즘 이게 핫하더라",
        ]
        return random.choice(comments)
```

- [ ] **Step 2: 테스트 작성**

```python
from worker.warmup import WarmupExecutor

def test_pick_video_count_day1():
    from unittest.mock import MagicMock
    session = MagicMock()
    executor = WarmupExecutor(session, day=1)
    for _ in range(20):
        count = executor._pick_video_count()
        assert 1 <= count <= 2

def test_pick_video_count_day2():
    from unittest.mock import MagicMock
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    for _ in range(20):
        count = executor._pick_video_count()
        assert 2 <= count <= 3

def test_pick_comment_count_day1():
    from unittest.mock import MagicMock
    session = MagicMock()
    executor = WarmupExecutor(session, day=1)
    assert executor._pick_comment_count() == 0

def test_pick_comment_count_day2():
    from unittest.mock import MagicMock
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    for _ in range(20):
        count = executor._pick_comment_count()
        assert 1 <= count <= 2

def test_generate_casual_comment():
    from unittest.mock import MagicMock
    session = MagicMock()
    executor = WarmupExecutor(session, day=2)
    comment = executor._generate_casual_comment()
    assert isinstance(comment, str)
    assert len(comment) > 0

def test_like_probability():
    from unittest.mock import MagicMock
    session = MagicMock()
    e1 = WarmupExecutor(session, day=1)
    e2 = WarmupExecutor(session, day=2)
    assert e1._like_probability() == 0.3
    assert e2._like_probability() == 0.5
```

- [ ] **Step 3: 테스트 실행 + Commit**

```bash
.venv/bin/python -m pytest tests/test_warmup.py -v
git add worker/warmup.py tests/test_warmup.py
git commit -m "feat: 워밍업 실행기 (Day 1~3 점진적 활동)"
```

---

### Task 6: Executor 스텁 → 실제 구현으로 교체

**Files:**
- Modify: `worker/executor.py`
- Modify: `worker/app.py`

- [ ] **Step 1: executor.py 교체**

기존 스텁 핸들러를 실제 브라우저 동작으로 교체:

```python
"""태스크 실행기 — 실제 브라우저 자동화."""
import json
import random
from hydra.browser.actions import (
    random_delay, post_comment, post_reply,
    click_like_button, scroll_to_comments, watch_video,
    handle_ad, check_ghost,
)
from worker.mouse import click_with_mouse_move
from worker.session import WorkerSession

class TaskExecutor:
    """태스크를 받아서 브라우저로 실행."""

    def __init__(self):
        self.handlers = {
            "comment": self._handle_comment,
            "reply": self._handle_reply,
            "like": self._handle_like,
            "like_boost": self._handle_like_boost,
            "subscribe": self._handle_subscribe,
            "warmup": self._handle_warmup,
            "ghost_check": self._handle_ghost_check,
            "login": self._handle_login,
            "channel_setup": self._handle_channel_setup,
        }

    async def execute(self, task: dict, session: WorkerSession) -> str:
        """태스크 실행. 세션이 열려있는 상태에서 호출."""
        task_type = task["task_type"]
        payload = json.loads(task.get("payload") or "{}")
        handler = self.handlers.get(task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task_type}")
        return await handler(task, payload, session)

    async def _handle_comment(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """댓글 작성."""
        page = session.browser.page
        video_id = payload.get("video_id", "")
        text = payload.get("text", "")

        # 영상 접속
        await self._navigate_to_video(session, video_id)

        # 광고 처리
        await handle_ad(page)

        # 짧은 시청 (2~5초)
        await watch_video(page, random.randint(2, 5))

        # 댓글 영역으로 스크롤
        await scroll_to_comments(page)

        # 기존 댓글 읽기 행동 (3~10초)
        await random_delay(3.0, 10.0)

        # 댓글 작성
        comment_id = await post_comment(page, text)

        return json.dumps({
            "action": "comment",
            "video_id": video_id,
            "youtube_comment_id": comment_id,
        })

    async def _handle_reply(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """대댓글 작성."""
        page = session.browser.page
        video_id = payload.get("video_id", "")
        text = payload.get("text", "")
        target = payload.get("target", "")

        await self._navigate_to_video(session, video_id)
        await handle_ad(page)
        await scroll_to_comments(page)
        await random_delay(3.0, 8.0)

        # 대상 댓글에 대댓글
        comment_id = await post_reply(page, f"[data-comment-id='{target}']", text)

        return json.dumps({
            "action": "reply",
            "video_id": video_id,
            "youtube_comment_id": comment_id,
        })

    async def _handle_like(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """영상 좋아요."""
        page = session.browser.page
        video_id = payload.get("video_id", "")

        await self._navigate_to_video(session, video_id)
        await handle_ad(page)
        await watch_video(page, random.randint(5, 30))
        await click_like_button(page, target="video")

        return json.dumps({"action": "like", "video_id": video_id})

    async def _handle_like_boost(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """댓글 좋아요 부스트."""
        page = session.browser.page
        video_id = payload.get("video_id", "")
        target_comment_id = payload.get("target_comment_id", "")

        await self._navigate_to_video(session, video_id)
        await handle_ad(page)
        await watch_video(page, random.randint(5, 20))
        await scroll_to_comments(page)

        # 주변 댓글 좋아요 (위장, 2~4개)
        comment_likes = page.locator("ytd-comment-thread-renderer #like-button button")
        count = await comment_likes.count()
        camouflage = random.randint(2, 4)
        for i in range(min(camouflage, count)):
            idx = random.randint(0, min(count - 1, 10))
            try:
                await comment_likes.nth(idx).click()
                await random_delay(1.0, 3.0)
            except Exception:
                pass

        # 대상 댓글 좋아요
        if target_comment_id:
            target = page.locator(f"[data-comment-id='{target_comment_id}'] #like-button button")
            try:
                await target.click()
            except Exception:
                pass

        return json.dumps({"action": "like_boost", "video_id": video_id})

    async def _handle_subscribe(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """채널 구독."""
        page = session.browser.page
        video_id = payload.get("video_id", "")

        await self._navigate_to_video(session, video_id)
        subscribe_btn = page.locator("ytd-subscribe-button-renderer button")
        try:
            await subscribe_btn.first.click()
        except Exception:
            pass

        return json.dumps({"action": "subscribe", "video_id": video_id})

    async def _handle_warmup(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """워밍업 세션."""
        from worker.warmup import WarmupExecutor
        day = payload.get("day", 1)
        persona = payload.get("persona")
        executor = WarmupExecutor(session, day=day, persona=persona)
        result = await executor.run()
        return json.dumps(result)

    async def _handle_ghost_check(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """고스트 체크."""
        page = session.browser.page
        video_id = payload.get("video_id", "")
        comment_id = payload.get("youtube_comment_id", "")

        await self._navigate_to_video(session, video_id)
        await scroll_to_comments(page)

        # 최신순 전환
        sort_btn = page.locator("#sort-menu tp-yt-paper-button, #sort-menu button")
        try:
            await sort_btn.first.click()
            await random_delay(0.5, 1.0)
            newest = page.locator("tp-yt-paper-listbox a, div[role='option']").nth(1)
            await newest.click()
            await random_delay(2.0, 4.0)
        except Exception:
            pass

        result = await check_ghost(page, comment_id)

        return json.dumps({
            "action": "ghost_check",
            "video_id": video_id,
            "comment_id": comment_id,
            "result": result,
        })

    async def _handle_login(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """자동 로그인."""
        from worker.login import auto_login
        page = session.browser.page
        success = await auto_login(
            page,
            email=payload.get("email", ""),
            password=payload.get("password", ""),
            totp_secret=payload.get("totp_secret"),
        )
        return json.dumps({"action": "login", "success": success})

    async def _handle_channel_setup(self, task: dict, payload: dict, session: WorkerSession) -> str:
        """유튜브 채널 설정 (이름, 아바타)."""
        page = session.browser.page

        # YouTube Studio 접속
        await page.goto("https://studio.youtube.com")
        await random_delay(3.0, 5.0)

        # 채널 이름 설정 등은 추후 구체화
        return json.dumps({"action": "channel_setup", "status": "placeholder"})

    async def _navigate_to_video(self, session: WorkerSession, video_id: str):
        """영상으로 이동 (검색 or 직접 URL)."""
        page = session.browser.page

        # 70% 직접 URL (워밍업/부스트에서는 직접이 실용적)
        # 작업 모드에서는 검색 비율 높일 수 있음
        use_direct = random.random() < 0.7

        if use_direct:
            await page.goto(f"https://www.youtube.com/watch?v={video_id}")
        else:
            # TODO: 검색으로 영상 찾기 (작업 모드에서 구현)
            await page.goto(f"https://www.youtube.com/watch?v={video_id}")

        await random_delay(2.0, 4.0)
```

NOTE: `execute()` 메서드가 이제 `async`이고 `session` 파라미터를 받음. app.py도 수정 필요.

- [ ] **Step 2: app.py 수정 — 세션 기반 실행으로 전환**

`worker/app.py`의 `_execute_task`를 세션 기반으로 변경:

```python
# _tick 메서드를 세션 기반으로 변경:

async def _execute_session(self, tasks: list[dict], profile_id: str, account_id: int):
    """한 계정의 세션 — 여러 태스크를 자연스럽게 실행."""
    session = WorkerSession(profile_id, account_id, device_id=config.adb_device_id)

    if not await session.start():
        # 세션 시작 실패 — 모든 태스크 실패 보고
        for task in tasks:
            self.client.fail_task(task["id"], "Session start failed")
        return

    try:
        for task in tasks:
            if not await session.should_continue():
                break

            # 자연 브라우징 (첫 태스크 제외)
            if session.tasks_completed > 0:
                await session.do_natural_browsing()

            # 태스크 실행
            try:
                result = await self.executor.execute(task, session)
                self.client.complete_task(task["id"], result)
                session.tasks_completed += 1
                print(f"[Worker] Task {task['id']} completed")
            except Exception as e:
                self.client.fail_task(task["id"], str(e))
                print(f"[Worker] Task {task['id']} failed: {e}")
    finally:
        await session.close()
```

Add `import asyncio` and update `_tick` to use `asyncio.run()` for async execution. Add `from worker.session import WorkerSession` import.

Also add to config.py:
```python
self.adb_device_id = os.getenv("HYDRA_ADB_DEVICE_ID", "")
```

- [ ] **Step 3: Commit**

```bash
git add worker/executor.py worker/app.py worker/config.py
git commit -m "feat: Executor 스텁 → 실제 브라우저 자동화 (세션 기반)"
```

---

### Task 7: Worker 모델에 역할 컬럼 추가

**Files:**
- Modify: `hydra/db/models.py`
- Modify: `hydra/services/task_service.py`

- [ ] **Step 1: Worker 모델에 역할 컬럼 추가**

```python
# Worker 모델에 추가:
allow_preparation = Column(Boolean, default=False)
allow_campaign = Column(Boolean, default=True)
```

- [ ] **Step 2: task_service.py의 fetch_tasks에서 역할 필터링**

```python
# fetch_tasks에서 태스크 배정 시 워커 역할 확인:
PREPARATION_TYPES = {"login", "channel_setup", "warmup"}

# 기존 필터에 추가:
for task in tasks:
    # 역할 체크
    if task.task_type in PREPARATION_TYPES and not worker.allow_preparation:
        continue
    if task.task_type not in PREPARATION_TYPES and not worker.allow_campaign:
        continue
    # ... 기존 잠금 체크 ...
```

- [ ] **Step 3: Alembic 마이그레이션**

Run: `alembic revision --autogenerate -m "worker_role_columns"`
Run: `alembic upgrade head`

- [ ] **Step 4: Commit**

```bash
git add hydra/db/models.py hydra/services/task_service.py alembic/
git commit -m "feat: Worker 역할 (준비/캠페인) 필터링"
```

---

### Task 8: 전체 테스트 + 정리

- [ ] **Step 1: 전체 테스트 실행**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: 모든 테스트 PASSED

- [ ] **Step 2: 최종 Commit**

```bash
git add -A
git commit -m "feat: 브라우저 자동화 엔진 — 워밍업 모드 실행 가능"
```
