from hydra.services.background import BackgroundScheduler


def test_scheduler_init():
    s = BackgroundScheduler()
    assert s.running is False
    assert "worker_health" in s.intervals
    assert "auto_campaign" in s.intervals


def test_scheduler_intervals():
    s = BackgroundScheduler()
    assert s.intervals["worker_health"] == 30
    assert s.intervals["auto_campaign"] == 300
