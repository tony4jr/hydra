"""서버 백그라운드 작업 — 주기적 실행."""
import asyncio
from datetime import datetime, UTC
from hydra.db.session import SessionLocal
from hydra.services.auto_scheduler import auto_create_campaigns, get_brands_needing_campaigns
from hydra.services.worker_service import check_stale_workers
from hydra.services.alert_service import alert_worker_disconnected


class BackgroundScheduler:
    """서버 백그라운드 스케줄러."""

    def __init__(self):
        self.running = False
        self.intervals = {
            "worker_health": 30,          # 30초마다 워커 상태 체크
            "auto_campaign": 300,         # 5분마다 자동 캠페인
        }
        self._last_run = {}

    async def start(self):
        """백그라운드 스케줄러 시작."""
        self.running = True
        print("[Scheduler] Started")
        while self.running:
            try:
                await self._tick()
            except Exception as e:
                print(f"[Scheduler] Error: {e}")
            await asyncio.sleep(10)  # 10초마다 체크

    async def _tick(self):
        now = datetime.now(UTC)

        for task_name, interval in self.intervals.items():
            last = self._last_run.get(task_name)
            if last and (now - last).total_seconds() < interval:
                continue

            self._last_run[task_name] = now

            if task_name == "worker_health":
                await self._check_workers()
            elif task_name == "auto_campaign":
                await self._auto_campaigns()

    async def _check_workers(self):
        """워커 상태 체크 — 오프라인 감지."""
        db = SessionLocal()
        try:
            stale = check_stale_workers(db, timeout_seconds=60)
            for worker in stale:
                await alert_worker_disconnected(worker.name)
        finally:
            db.close()

    async def _auto_campaigns(self):
        """자동 캠페인 생성."""
        db = SessionLocal()
        try:
            brands = get_brands_needing_campaigns(db)
            if brands:
                created = auto_create_campaigns(db, max_per_run=3)
                if created:
                    print(f"[Scheduler] Auto-created {len(created)} campaigns")
        finally:
            db.close()

    def stop(self):
        self.running = False


scheduler = BackgroundScheduler()
