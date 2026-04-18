def test_task_type_has_create_profile():
    from hydra.core.enums import TaskType
    assert TaskType.CREATE_PROFILE == "create_profile"
    assert TaskType.RETIRE_PROFILE == "retire_profile"


def test_ip_rotation_failed_is_runtime_error():
    from hydra.infra.ip_errors import IPRotationFailed
    assert issubclass(IPRotationFailed, RuntimeError)
    err = IPRotationFailed("test")
    assert str(err) == "test"


def test_new_config_defaults():
    from hydra.core.config import settings
    assert settings.adspower_group_id == "0"
    assert settings.adspower_profile_quota == 100
    assert settings.enable_fingerprint_bundle is True
    assert settings.ip_rotation_cooldown_minutes == 30
    assert settings.ip_rotation_max_attempts == 3
    assert settings.ip_rotation_task_retry_max == 5
    assert settings.ip_rotation_reschedule_min == 5
    assert settings.ip_rotation_reschedule_max == 10
