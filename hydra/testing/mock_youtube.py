"""Mock YouTube — staging 검증용 페이지 + API 응답 시뮬레이터.

목적: 실제 YouTube 트래픽 없이 worker session pipeline (login_check / IP rotate /
adspower_open / cdp_connect / video_goto / compose / type / submit) 의 단계별 동작을
재현 가능하게 한다.

핵심 시나리오:
1. happy_path — 모든 phase 성공.
2. captcha_at_login — 로그인 단계 captcha.
3. ghost_comment — submit 후 댓글이 다른 계정에 보이지 않는 (ghost).
4. rate_limited — 짧은 시간 다수 댓글 시도 시 거부.
5. video_unavailable — 영상이 deleted/private.
6. slow_load_<phase> — 특정 phase 가 timeout 만큼 hang.

사용:
    from hydra.testing.mock_youtube import MockYouTube
    yt = MockYouTube(scenario="happy_path")
    response = yt.post_comment(video_id="abc", text="hi", account_id=1)
    assert response.status == "ok"

CI 통합: tests/test_pr_k_mock_youtube.py 가 worker pipeline 을 mock 으로 실행 +
서버 상태 검증 (worker_progress phase 시퀀스, last_phase, account_status 등).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from typing import Any, Optional


@dataclass
class MockYouTubeResponse:
    status: str       # "ok" | "captcha" | "rate_limited" | "ghost" | "unavailable" | "timeout"
    comment_id: Optional[str] = None
    error: Optional[str] = None
    delay_sec: float = 0.0
    metadata: dict = field(default_factory=dict)


SCENARIOS = (
    "happy_path",
    "captcha_at_login",
    "ghost_comment",
    "rate_limited",
    "video_unavailable",
    "slow_load_video_goto",
    "slow_load_compose",
    "slow_load_submit",
)


class MockYouTube:
    """Stateful mock of YouTube as seen by the worker.

    - 각 인스턴스는 독립적 상태 (계정별 행동 이력, 댓글 ID 카운터).
    - scenario 로 결정적 결과 제어.
    - phase 별 지연 (slow_load_*) — asyncio.sleep 로 wait_for timeout 트리거.
    """

    def __init__(self, scenario: str = "happy_path"):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.scenario = scenario
        self.comment_counter = 0
        self.account_actions: dict[int, list[dict]] = {}
        self.comments_db: dict[str, dict] = {}  # video_id → list of comment dicts (simplified to id key)
        self._created_at = datetime.now(UTC)

    async def login_check(self, account_id: int) -> MockYouTubeResponse:
        if self.scenario == "captcha_at_login":
            return MockYouTubeResponse(status="captcha", error="login_captcha_persistent")
        return MockYouTubeResponse(status="ok")

    async def navigate_to_video(self, video_id: str) -> MockYouTubeResponse:
        if self.scenario == "video_unavailable":
            return MockYouTubeResponse(status="unavailable", error="video_deleted_or_private")
        if self.scenario == "slow_load_video_goto":
            # phase_config 의 video_goto timeout 60s 보다 길게 대기 — wait_for timeout 트리거.
            await asyncio.sleep(120)
        return MockYouTubeResponse(status="ok")

    async def compose_comment(self, text: str) -> MockYouTubeResponse:
        if self.scenario == "slow_load_compose":
            await asyncio.sleep(240)  # > 180s compose timeout
        return MockYouTubeResponse(status="ok", delay_sec=0.2)

    async def submit_comment(
        self, video_id: str, text: str, account_id: int, parent_id: Optional[str] = None
    ) -> MockYouTubeResponse:
        if self.scenario == "rate_limited":
            # 같은 계정 1분 내 2건 시도 시 거부.
            recent = [
                a for a in self.account_actions.get(account_id, [])
                if a["at"] >= datetime.now(UTC) - timedelta(minutes=1)
            ]
            if len(recent) >= 1:
                return MockYouTubeResponse(status="rate_limited", error="comment_too_frequent")
        if self.scenario == "slow_load_submit":
            await asyncio.sleep(60)  # > 30s submit timeout
        if self.scenario == "ghost_comment":
            # 댓글 작성은 보이지만 다른 viewer 에겐 안 보임.
            self.comment_counter += 1
            cid = f"ghost-{self.comment_counter}"
            self.comments_db[cid] = {
                "video_id": video_id, "text": text, "account_id": account_id,
                "visible": False, "parent_id": parent_id,
            }
            self._record_action(account_id, "submit", cid)
            return MockYouTubeResponse(status="ghost", comment_id=cid, metadata={"visible": False})
        # happy_path 또는 slow_load_* 가 통과한 경우.
        self.comment_counter += 1
        cid = f"cmt-{self.comment_counter}"
        self.comments_db[cid] = {
            "video_id": video_id, "text": text, "account_id": account_id,
            "visible": True, "parent_id": parent_id,
        }
        self._record_action(account_id, "submit", cid)
        return MockYouTubeResponse(status="ok", comment_id=cid)

    async def like_comment(self, comment_id: str, account_id: int) -> MockYouTubeResponse:
        comment = self.comments_db.get(comment_id)
        if comment is None:
            return MockYouTubeResponse(status="unavailable", error="comment_not_found")
        if comment.get("liked_by") is None:
            comment["liked_by"] = set()
        comment["liked_by"].add(account_id)
        self._record_action(account_id, "like", comment_id)
        return MockYouTubeResponse(status="ok")

    def _record_action(self, account_id: int, action_type: str, ref: str) -> None:
        self.account_actions.setdefault(account_id, []).append({
            "at": datetime.now(UTC),
            "action": action_type,
            "ref": ref,
        })

    # ───── inspection (CI test assertions) ─────

    def get_visible_comments(self, video_id: str) -> list[dict]:
        return [c for c in self.comments_db.values()
                if c["video_id"] == video_id and c.get("visible", True)]

    def get_comments_by_account(self, account_id: int) -> list[dict]:
        return [c for c in self.comments_db.values() if c["account_id"] == account_id]

    def total_likes_on_comment(self, comment_id: str) -> int:
        c = self.comments_db.get(comment_id)
        if not c:
            return 0
        return len(c.get("liked_by", set()))


class MockBrowserSession:
    """Worker 의 BrowserSession 자리에 끼울 수 있는 mock.

    실제 Playwright / AdsPower 호출 없이 MockYouTube 호출로 대체.
    """

    def __init__(self, profile_id: str, yt: MockYouTube):
        self.profile_id = profile_id
        self.yt = yt
        self.page = self  # 단순화: page 객체 역할도 같이.
        self.started = False

    async def start(self):
        # AdsPower 시작 시뮬레이션 — 짧은 대기 후 ok.
        await asyncio.sleep(0.05)
        self.started = True

    async def goto(self, url: str):
        if "shorts" in url or "watch" in url or "v=" in url:
            video_id = url.rsplit("/", 1)[-1].split("?")[0].split("&")[0]
            if "v=" in url:
                video_id = url.split("v=")[1].split("&")[0]
            r = await self.yt.navigate_to_video(video_id)
            if r.status != "ok":
                raise RuntimeError(f"goto failed: {r.error}")
        # else: home / shorts feed 등 — 그냥 통과.
        await asyncio.sleep(0.02)

    async def close(self):
        self.started = False
