from hydra.services.realtime import ConnectionManager


def test_connection_manager_init():
    mgr = ConnectionManager()
    assert len(mgr.active_connections) == 0
