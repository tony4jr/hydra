"""T17 다영상 캠페인 + T20 부스트 타이밍."""
import json
from datetime import UTC, datetime, timedelta

import jwt as _jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import hydra.db.session as session_mod
from hydra.db.models import (
    Account, Base, Brand, Campaign, CampaignVideo, Task, Video, Worker,
)


@pytest.fixture
def env(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(session_mod, "engine", engine)
    monkeypatch.setattr(session_mod, "SessionLocal", TestSession)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-123456789")
    monkeypatch.setenv("HYDRA_ENCRYPTION_KEY", "inH7FBGqG6Xdp/DZU7s1CXal+EreHfYZrnOn9xbM0C4=")

    db = TestSession()
    brand = Brand(name="b1")
    db.add(brand); db.flush()
    camp = Campaign(brand_id=brand.id, scenario="A", name="cam1")
    db.add(camp); db.flush()
    # videos
    for vid in ["v1", "v2", "v3"]:
        db.add(Video(id=vid, title=f"t-{vid}",
                     url=f"https://www.youtube.com/watch?v={vid}"))
    # accounts + worker
    for i in range(3):
        db.add(Account(gmail=f"u{i}@x.com", password="enc",
                       adspower_profile_id=f"k{i}", status="active"))
    db.add(Worker(name="w1", status="online"))
    db.add(Worker(name="w2", status="online"))
    db.commit()
    cid = camp.id
    db.close()

    from hydra.web.app import app
    client = TestClient(app)
    now = datetime.now(UTC)
    admin_jwt = _jwt.encode(
        {"user_id": 1, "role": "admin", "iat": now, "exp": now + timedelta(hours=1)},
        "test-jwt-secret-123456789", algorithm="HS256",
    )
    yield {"client": client, "admin_jwt": admin_jwt, "Session": TestSession,
           "campaign_id": cid}
    engine.dispose()


def _h(env): return {"Authorization": f"Bearer {env['admin_jwt']}"}


def test_add_videos_to_campaign(env):
    r = env["client"].post(
        f"/api/campaigns/{env['campaign_id']}/videos",
        headers=_h(env),
        json=[
            {"video_id": "v1", "funnel_stage": "awareness", "target_count": 10, "priority": 5},
            {"video_id": "v2", "funnel_stage": "consideration", "target_count": 5},
        ],
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert items[0]["video_id"] == "v1"
    assert items[0]["target_count"] == 10
    assert items[0]["progress_pct"] == 0.0


def test_add_unregistered_video_400(env):
    r = env["client"].post(
        f"/api/campaigns/{env['campaign_id']}/videos",
        headers=_h(env),
        json=[{"video_id": "nonexistent", "target_count": 1}],
    )
    assert r.status_code == 400


def test_list_campaign_videos_sorted_by_priority(env):
    env["client"].post(f"/api/campaigns/{env['campaign_id']}/videos", headers=_h(env), json=[
        {"video_id": "v1", "target_count": 1, "priority": 1},
        {"video_id": "v2", "target_count": 1, "priority": 5},
        {"video_id": "v3", "target_count": 1, "priority": 3},
    ])
    r = env["client"].get(f"/api/campaigns/{env['campaign_id']}/videos", headers=_h(env))
    items = r.json()
    assert [v["video_id"] for v in items] == ["v2", "v3", "v1"]  # priority desc


def test_remove_video(env):
    env["client"].post(f"/api/campaigns/{env['campaign_id']}/videos", headers=_h(env),
                       json=[{"video_id": "v1", "target_count": 1}])
    r = env["client"].delete(f"/api/campaigns/{env['campaign_id']}/videos/v1", headers=_h(env))
    assert r.status_code == 200
    listed = env["client"].get(f"/api/campaigns/{env['campaign_id']}/videos", headers=_h(env)).json()
    assert listed == []


def test_schedule_boosts_creates_like_tasks(env):
    cid = env["campaign_id"]
    db = env["Session"]()
    # account 1 + worker 1 의 done comment 태스크 2건
    accounts = db.query(Account).all()
    workers = db.query(Worker).all()
    for i in range(2):
        db.add(Task(
            campaign_id=cid, account_id=accounts[i].id, worker_id=workers[0].id,
            task_type="comment", status="done",
            payload=json.dumps({"video_id": "v1"}),
        ))
    db.commit(); db.close()

    r = env["client"].post(
        f"/api/campaigns/{cid}/schedule-boosts",
        headers=_h(env),
        json={"delay_min_minutes": 5, "delay_max_minutes": 30, "likes_per_comment": 3},
    )
    body = r.json()
    assert body["scheduled"] == 6  # 2 댓글 × 3 like

    db = env["Session"]()
    likes = db.query(Task).filter(Task.task_type == "like", Task.campaign_id == cid).all()
    assert len(likes) == 6
    # 각 like 가 다른 scheduled_at + 미래 시각
    # SQLite 는 UTC 로 저장하지만 naive 로 반환 → datetime.utcnow() 와 비교
    from datetime import datetime as _dt
    now_utc_naive = _dt.utcnow()
    for like in likes:
        assert like.scheduled_at is not None
        sat = like.scheduled_at
        if sat.tzinfo is not None:
            sat = sat.replace(tzinfo=None)
        assert sat > now_utc_naive
        payload = json.loads(like.payload)
        assert "source_comment_id" in payload
    db.close()


def test_schedule_boosts_avoids_duplicate(env):
    cid = env["campaign_id"]
    db = env["Session"]()
    acc = db.query(Account).first()
    w = db.query(Worker).first()
    db.add(Task(
        campaign_id=cid, account_id=acc.id, worker_id=w.id,
        task_type="comment", status="done",
        payload=json.dumps({"video_id": "v1"}),
    )); db.commit(); db.close()

    # 두 번 발행 — 두 번째는 dedupe
    env["client"].post(f"/api/campaigns/{cid}/schedule-boosts", headers=_h(env),
                       json={"likes_per_comment": 1})
    r2 = env["client"].post(f"/api/campaigns/{cid}/schedule-boosts", headers=_h(env),
                            json={"likes_per_comment": 1})
    body = r2.json()
    assert body["scheduled"] == 0
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "already scheduled"


def test_admin_auth_required(env):
    cid = env["campaign_id"]
    assert env["client"].get(f"/api/campaigns/{cid}/videos").status_code == 401
    assert env["client"].post(f"/api/campaigns/{cid}/schedule-boosts", json={}).status_code == 401
