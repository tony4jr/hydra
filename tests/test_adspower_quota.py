import pytest
from unittest.mock import patch


def test_get_profile_count_returns_total():
    from hydra.browser.adspower import AdsPowerClient
    c = AdsPowerClient(base_url="http://d", api_key="k")
    with patch.object(c, "_get", return_value={"total": 42, "list": []}):
        assert c.get_profile_count() == 42


def test_quota_report_shows_used_and_quota(db_session, monkeypatch):
    from hydra.web.routes.accounts import compute_quota_report
    from hydra.db.models import Account

    a = Account(gmail="q1@g.com", password="x",
                adspower_profile_id="p1", status="profile_set")
    db_session.add(a)
    db_session.commit()

    monkeypatch.setattr(
        "hydra.web.routes.accounts.adspower.get_profile_count",
        lambda: 1,
    )
    from hydra.core.config import settings
    monkeypatch.setattr(settings, "adspower_profile_quota", 100)

    report = compute_quota_report(db_session)
    assert report["adspower_count"] == 1
    assert report["linked_accounts"] == 1
    assert report["quota"] == 100
    assert report["used_ratio"] == 0.01
