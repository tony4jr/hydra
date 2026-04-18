import pytest
from unittest.mock import patch


def test_adspower_errors_exist():
    from hydra.browser.adspower_errors import AdsPowerAPIError, AdsPowerQuotaExceeded
    assert issubclass(AdsPowerAPIError, RuntimeError)
    assert issubclass(AdsPowerQuotaExceeded, AdsPowerAPIError)


def test_create_profile_accepts_fingerprint_config():
    """create_profile forwards fingerprint_config dict to the API."""
    from hydra.browser.adspower import AdsPowerClient
    client = AdsPowerClient(base_url="http://dummy", api_key="k")

    fp = {"random_ua": {"ua_system_version": ["Windows 11"]}, "timezone": "Asia/Seoul"}
    captured = {}

    def fake_post(path, json_body):
        captured["path"] = path
        captured["body"] = json_body
        return {"id": "fake123"}

    with patch.object(client, "_post", side_effect=fake_post):
        pid = client.create_profile(
            name="hydra_1_test", group_id="0",
            fingerprint_config=fp, remark="test",
        )
    assert pid == "fake123"
    assert captured["path"] == "/api/v1/user/create"
    assert captured["body"]["name"] == "hydra_1_test"
    assert captured["body"]["group_id"] == "0"
    assert captured["body"]["remark"] == "test"
    assert captured["body"]["fingerprint_config"] == fp
    assert captured["body"]["user_proxy_config"] == {"proxy_soft": "no_proxy"}


def test_create_profile_quota_exceeded_translates_error():
    from hydra.browser.adspower import AdsPowerClient
    from hydra.browser.adspower_errors import AdsPowerQuotaExceeded

    client = AdsPowerClient(base_url="http://dummy", api_key="k")

    def fake_post(path, json_body):
        raise RuntimeError("AdsPower error: Account package limit exceeded")

    with patch.object(client, "_post", side_effect=fake_post):
        with pytest.raises(AdsPowerQuotaExceeded):
            client.create_profile(
                name="n", group_id="0",
                fingerprint_config={"timezone": "Asia/Seoul"},
            )
