"""태스크 실행기 — 태스크 유형별 핸들러 디스패치."""
import json
import random
import time
from worker.adspower import AdsPowerClient


class TaskExecutor:
    def __init__(self):
        self.adspower = AdsPowerClient()
        self.handlers = {
            "comment": self._handle_comment,
            "reply": self._handle_reply,
            "like": self._handle_like,
            "like_boost": self._handle_like_boost,
            "subscribe": self._handle_subscribe,
            "warmup": self._handle_warmup,
            "ghost_check": self._handle_ghost_check,
        }

    def execute(self, task: dict) -> str:
        """태스크 실행. 결과 문자열 반환."""
        task_type = task["task_type"]
        payload = json.loads(task.get("payload") or "{}")
        handler = self.handlers.get(task_type)
        if not handler:
            raise ValueError(f"Unknown task type: {task_type}")
        return handler(task, payload)

    def _handle_comment(self, task: dict, payload: dict) -> str:
        """댓글 작성."""
        video_id = payload.get("video_id", "")
        text = payload.get("text", "")
        # 실제 구현: AdsPower 프로필 열기 → YouTube 접속 → 댓글 작성
        # 지금은 인터페이스만 정의
        print(f"  [Executor] Comment on {video_id}: {text[:30]}...")
        return json.dumps({"action": "comment", "video_id": video_id})

    def _handle_reply(self, task: dict, payload: dict) -> str:
        """대댓글 작성."""
        video_id = payload.get("video_id", "")
        target = payload.get("target", "")
        print(f"  [Executor] Reply on {video_id} to {target}")
        return json.dumps({"action": "reply", "video_id": video_id, "target": target})

    def _handle_like(self, task: dict, payload: dict) -> str:
        """영상 좋아요."""
        video_id = payload.get("video_id", "")
        print(f"  [Executor] Like video {video_id}")
        return json.dumps({"action": "like", "video_id": video_id})

    def _handle_like_boost(self, task: dict, payload: dict) -> str:
        """댓글 좋아요 부스트."""
        video_id = payload.get("video_id", "")
        target_step = payload.get("target_step", "")
        print(f"  [Executor] Like boost on {video_id} step {target_step}")
        return json.dumps({"action": "like_boost", "video_id": video_id})

    def _handle_subscribe(self, task: dict, payload: dict) -> str:
        """채널 구독."""
        video_id = payload.get("video_id", "")
        print(f"  [Executor] Subscribe via {video_id}")
        return json.dumps({"action": "subscribe", "video_id": video_id})

    def _handle_warmup(self, task: dict, payload: dict) -> str:
        """워밍업 세션."""
        print(f"  [Executor] Warmup session")
        return json.dumps({"action": "warmup"})

    def _handle_ghost_check(self, task: dict, payload: dict) -> str:
        """고스트 체크."""
        video_id = payload.get("video_id", "")
        print(f"  [Executor] Ghost check on {video_id}")
        return json.dumps({"action": "ghost_check", "video_id": video_id})
