def test_task_type_has_create_profile():
    from hydra.core.enums import TaskType
    assert TaskType.CREATE_PROFILE == "create_profile"
    assert TaskType.RETIRE_PROFILE == "retire_profile"


def test_ip_rotation_failed_is_runtime_error():
    from hydra.infra.ip_errors import IPRotationFailed
    assert issubclass(IPRotationFailed, RuntimeError)
    err = IPRotationFailed("test")
    assert str(err) == "test"
