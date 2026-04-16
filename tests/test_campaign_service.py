import json
import pytest
from hydra.db.models import Brand, Video, Preset, Task
from hydra.services.campaign_service import (
    create_campaign_with_tasks,
    create_direct_campaign,
    extract_video_id,
)


PRESET_A_STEPS = json.dumps([
    {
        "step_number": 1,
        "type": "comment",
        "role": "seed",
        "tone": "casual",
        "target": "main",
        "delay_min": 0,
        "delay_max": 5,
        "like_count": 5,
    },
])

PRESET_B_STEPS = json.dumps([
    {
        "step_number": 1,
        "type": "comment",
        "role": "seed",
        "tone": "casual",
        "target": "main",
        "delay_min": 0,
        "delay_max": 3,
        "like_count": 3,
    },
    {
        "step_number": 2,
        "type": "reply",
        "role": "witness",
        "tone": "excited",
        "target": "step_1",
        "delay_min": 5,
        "delay_max": 15,
        "like_count": 0,
    },
    {
        "step_number": 3,
        "type": "comment",
        "role": "agree",
        "tone": "neutral",
        "target": "main",
        "delay_min": 10,
        "delay_max": 30,
        "like_count": 2,
    },
])


@pytest.fixture
def seeded_db(db_session):
    """Seed brand, video, and presets for campaign tests."""
    brand = Brand(id=1, name="TestBrand")
    db_session.add(brand)

    video = Video(id="test_video_123", url="https://www.youtube.com/watch?v=test_video_123")
    db_session.add(video)

    preset_a = Preset(name="Preset A", code="A", steps=PRESET_A_STEPS, is_system=True)
    preset_b = Preset(name="Preset B", code="B", steps=PRESET_B_STEPS, is_system=True)
    db_session.add_all([preset_a, preset_b])
    db_session.commit()

    return db_session


# ── 1. extract_video_id ──────────────────────────────────────────────

def test_extract_video_id():
    # Standard watch URL
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Short URL
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Shorts URL
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # With extra params
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30") == "dQw4w9WgXcQ"
    # /v/ style
    assert extract_video_id("https://www.youtube.com/v/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Invalid URL
    assert extract_video_id("https://example.com/not-a-video") is None
    # Empty
    assert extract_video_id("") is None


# ── 2. Preset A: 1 comment + 5 like_boost = 6 tasks ─────────────────

def test_create_campaign_with_tasks_preset_a(seeded_db):
    campaign = create_campaign_with_tasks(
        db=seeded_db,
        video_id="test_video_123",
        brand_id=1,
        preset_code="A",
    )
    assert campaign.status == "in_progress"
    assert campaign.scenario == "A"

    tasks = seeded_db.query(Task).filter(Task.campaign_id == campaign.id).all()
    comment_tasks = [t for t in tasks if t.task_type == "comment"]
    like_tasks = [t for t in tasks if t.task_type == "like_boost"]

    assert len(comment_tasks) == 1
    assert len(like_tasks) == 5
    assert len(tasks) == 6


# ── 3. Preset B: 3 steps (comment/reply/comment) + 3+0+2 likes = 8 tasks total

def test_create_campaign_with_tasks_preset_b(seeded_db):
    campaign = create_campaign_with_tasks(
        db=seeded_db,
        video_id="test_video_123",
        brand_id=1,
        preset_code="B",
    )
    tasks = seeded_db.query(Task).filter(Task.campaign_id == campaign.id).all()

    # 3 main tasks (comment, reply, comment) + 3 + 0 + 2 like_boosts = 8
    main_tasks = [t for t in tasks if t.task_type != "like_boost"]
    like_tasks = [t for t in tasks if t.task_type == "like_boost"]

    assert len(main_tasks) == 3
    assert len(like_tasks) == 5  # 3 + 0 + 2
    assert len(tasks) == 8


# ── 4. Randomness: two campaigns should have different scheduled_at ──

def test_create_campaign_tasks_have_random_scheduling(seeded_db):
    c1 = create_campaign_with_tasks(
        db=seeded_db,
        video_id="test_video_123",
        brand_id=1,
        preset_code="A",
    )
    c2 = create_campaign_with_tasks(
        db=seeded_db,
        video_id="test_video_123",
        brand_id=1,
        preset_code="A",
    )

    tasks1 = seeded_db.query(Task).filter(Task.campaign_id == c1.id).order_by(Task.id).all()
    tasks2 = seeded_db.query(Task).filter(Task.campaign_id == c2.id).order_by(Task.id).all()

    assert len(tasks1) == len(tasks2)

    # At least one pair should have different scheduled_at (extremely unlikely to be identical)
    any_diff = any(
        t1.scheduled_at != t2.scheduled_at for t1, t2 in zip(tasks1, tasks2)
    )
    assert any_diff, "All scheduled_at times are identical — randomness not working"


# ── 5. Direct campaign ──────────────────────────────────────────────

def test_create_direct_campaign(seeded_db):
    # Need video records for the FK constraint
    v1 = Video(id="abc12345678", url="https://www.youtube.com/watch?v=abc12345678")
    v2 = Video(id="xyz98765432", url="https://www.youtube.com/watch?v=xyz98765432")
    seeded_db.add_all([v1, v2])
    seeded_db.commit()

    urls = [
        "https://www.youtube.com/watch?v=abc12345678",
        "https://youtu.be/xyz98765432",
        "https://invalid-url.com",
    ]
    actions = {
        "brand_id": 1,
        "scenario": "direct",
        "like_count": 3,
        "comments": [
            {"text": "Great video!", "mode": "manual"},
            {"text": "Love this", "mode": "manual"},
        ],
        "subscribe": True,
    }

    campaigns = create_direct_campaign(seeded_db, urls, actions)

    # Invalid URL skipped → 2 campaigns
    assert len(campaigns) == 2

    for c in campaigns:
        tasks = seeded_db.query(Task).filter(Task.campaign_id == c.id).all()
        like_tasks = [t for t in tasks if t.task_type == "like"]
        comment_tasks = [t for t in tasks if t.task_type == "comment"]
        sub_tasks = [t for t in tasks if t.task_type == "subscribe"]

        assert len(like_tasks) == 3
        assert len(comment_tasks) == 2
        assert len(sub_tasks) == 1
        assert len(tasks) == 6  # 3 likes + 2 comments + 1 subscribe


# ── 6. Invalid preset raises ValueError ─────────────────────────────

def test_create_campaign_invalid_preset(seeded_db):
    with pytest.raises(ValueError, match="Preset 'NONEXISTENT' not found"):
        create_campaign_with_tasks(
            db=seeded_db,
            video_id="test_video_123",
            brand_id=1,
            preset_code="NONEXISTENT",
        )
