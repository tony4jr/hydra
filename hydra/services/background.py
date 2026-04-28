"""서버 백그라운드 작업 — 주기적 실행."""
import asyncio
from datetime import datetime, UTC
from hydra.db.session import SessionLocal
from hydra.db.models import Brand
from hydra.services.auto_scheduler import auto_create_campaigns, get_brands_needing_campaigns
from hydra.services.worker_service import check_stale_workers
from hydra.services.alert_service import alert_worker_disconnected


class BackgroundScheduler:
    """서버 백그라운드 스케줄러."""

    def __init__(self):
        self.running = False
        self.intervals = {
            "worker_health": 30,              # 30초마다 워커 상태 체크
            "m1_tick": 30,                    # 30초마다 sweep + campaign scan
            "auto_campaign": 300,             # 5분마다 자동 캠페인
            "collect_new_videos": 14400,      # 4시간마다 (초)
            "collect_popular_videos": 86400,  # 1일마다
            # Phase 1: 핫 키워드 5분 폴링 (poll_5min=True 키워드만)
            "phase1_poll_5min": 300,          # 5분
            "phase1_poll_30min": 1800,        # 30분
            "phase1_poll_daily": 86400,       # 1일 (03:00 KST)
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
            elif task_name == "m1_tick":
                await self._m1_tick()
            elif task_name == "auto_campaign":
                await self._auto_campaigns()
            elif task_name == "collect_new_videos":
                await self._collect_new()
            elif task_name == "collect_popular_videos":
                await self._collect_popular()
            elif task_name == "phase1_poll_5min":
                await self._phase1_poll('5min')
            elif task_name == "phase1_poll_30min":
                await self._phase1_poll('30min')
            elif task_name == "phase1_poll_daily":
                await self._phase1_poll('daily')

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

    async def _collect_new(self):
        """전략 1: 최신순 영상 수집 (4시간마다)."""
        db = SessionLocal()
        try:
            from hydra.services.video_collector import collect_new_videos
            brands = db.query(Brand).filter(
                Brand.status == "active",
                Brand.auto_campaign_enabled == True,
            ).all()
            for brand in brands:
                collected = collect_new_videos(db, brand.id)
                if collected:
                    print(f"[Scheduler] Collected {len(collected)} new videos for {brand.name}")
        finally:
            db.close()

    async def _collect_popular(self):
        """전략 2: 조회수순 영상 수집 (1일마다)."""
        db = SessionLocal()
        try:
            from hydra.services.video_collector import collect_popular_videos
            brands = db.query(Brand).filter(
                Brand.status == "active",
                Brand.auto_campaign_enabled == True,
            ).all()
            for brand in brands:
                collected = collect_popular_videos(db, brand.id)
                if collected:
                    print(f"[Scheduler] Collected {len(collected)} popular videos for {brand.name}")
        finally:
            db.close()

    async def _m1_tick(self):
        """M1-8: sweep stuck accounts + scan active accounts (campaign stub)."""
        try:
            await asyncio.to_thread(m1_tick)
        except Exception as e:
            print(f"[Scheduler] m1_tick failed: {e}")

    async def _phase1_poll(self, poll_type: str):
        """Phase 1 폴링 — keyword.poll_5min/poll_30min/poll_daily=True 인 키워드만.

        5분 폴링은 quota 90% 초과 시 자동 스킵.
        """
        try:
            await asyncio.to_thread(self._phase1_poll_sync, poll_type)
        except Exception as e:
            print(f"[Scheduler] phase1_poll {poll_type} failed: {e}")

    def _phase1_poll_sync(self, poll_type: str):
        from hydra.db.models import Keyword, VideoCollectionLog
        from hydra.services.youtube_quota import should_skip_5min_poll, record_usage
        from hydra.collection.youtube_api import _load_keys_from_db, search_videos
        from hydra.core.config import settings as app_settings
        from datetime import datetime, timedelta, UTC

        db = SessionLocal()
        try:
            # 5분 폴링은 quota throttle 체크
            if poll_type == "5min":
                keys = _load_keys_from_db() or app_settings.youtube_api_keys
                if should_skip_5min_poll(db, max(len(keys or []), 1)):
                    return

            poll_col = {
                "5min": Keyword.poll_5min,
                "30min": Keyword.poll_30min,
                "daily": Keyword.poll_daily,
            }[poll_type]

            keywords = (
                db.query(Keyword)
                .filter(
                    Keyword.status == "active",
                    Keyword.is_negative.is_(False),
                    poll_col.is_(True),
                )
                .all()
            )
            if not keywords:
                return

            # publishedAfter 윈도우
            window = {
                "5min": timedelta(hours=24),   # 24h 내 신규
                "30min": timedelta(days=7),    # 7일 내
                "daily": timedelta(days=365 * 5),  # 5년치
            }[poll_type]
            published_after = (datetime.now(UTC) - window).isoformat()

            # 정렬: 5min/30min 은 'date', daily 는 다중 (relevance/date/viewCount)
            orders = ["date"] if poll_type != "daily" else ["relevance", "date", "viewCount"]

            log = VideoCollectionLog(
                target_id=keywords[0].brand_id or 0,
                poll_type=poll_type,
                keywords_processed=0,
                api_calls_made=0,
                videos_found=0,
                videos_new=0,
                videos_updated=0,
                videos_blocked=0,
                started_at=datetime.now(UTC),
                status="running",
            )
            db.add(log); db.flush()

            from hydra.services.video_pipeline import process_video
            from hydra.db.models import Video

            for kw in keywords:
                if not kw.brand_id:
                    continue
                target_id = kw.brand_id
                for order in orders:
                    try:
                        results = search_videos(
                            kw.text, max_results=50, order=order,
                            published_after=published_after,
                        )
                        log.api_calls_made += 1
                        log.videos_found += len(results)
                        for r in results:
                            vid = r.get("video_id")
                            if not vid:
                                continue
                            v = db.get(Video, vid)
                            if v is None:
                                # 새 영상 — 메타 fetch 없이 스니펫만 저장 (process_video 가 후처리)
                                from datetime import datetime as _dt
                                pub = None
                                pub_str = r.get("published_at")
                                if pub_str:
                                    try:
                                        pub = _dt.fromisoformat(pub_str.replace("Z", "+00:00"))
                                    except (ValueError, AttributeError):
                                        pass
                                v = Video(
                                    id=vid,
                                    url=f"https://www.youtube.com/watch?v={vid}",
                                    title=r.get("title", ""),
                                    channel_id=r.get("channel_id", ""),
                                    channel_title=r.get("channel_title", ""),
                                    description=r.get("description", ""),
                                    published_at=pub,
                                    keyword_id=kw.id,
                                    state="pending",
                                    discovered_via=f"phase1_{poll_type}_{order}",
                                    discovery_keyword=kw.text,
                                )
                                db.add(v); db.flush()
                                log.videos_new += 1
                            result = process_video(db, v, target_id, keyword=kw)
                            if result == "blacklisted":
                                log.videos_blocked += 1
                        kw.last_searched_at = datetime.now(UTC)
                    except Exception as e:
                        print(f"[Phase1Poll {poll_type}] {kw.text} order={order} failed: {e}")
                log.keywords_processed += 1

            log.completed_at = datetime.now(UTC)
            log.status = "done"
            db.commit()

            if log.videos_new > 0 or log.videos_blocked > 0:
                print(f"[Phase1Poll {poll_type}] keywords={log.keywords_processed} new={log.videos_new} blocked={log.videos_blocked}")
        finally:
            db.close()

    def stop(self):
        self.running = False


def m1_tick() -> dict:
    """M1-8: orchestrator.sweep_stuck_accounts + campaign_stub.scan_active_accounts.

    기존 scheduler 의 주기 tick 에서 호출. 독립 함수라 테스트 용이.
    """
    from hydra.core.orchestrator import sweep_stuck_accounts
    from hydra.core.campaign_stub import scan_active_accounts
    from hydra.db import session as _s

    db = _s.SessionLocal()
    try:
        swept = sweep_stuck_accounts(db)
        scanned = scan_active_accounts(db)
        return {"swept": swept, "scanned": scanned}
    finally:
        db.close()


scheduler = BackgroundScheduler()
