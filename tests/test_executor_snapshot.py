"""Task M1-12: executor 가 AccountSnapshot 만으로 작동."""
import inspect


def test_executor_source_does_not_import_sessionlocal():
    """M1-12: worker/executor.py 에서 SessionLocal import 완전 제거."""
    import worker.executor as ex
    src = inspect.getsource(ex)
    assert "SessionLocal" not in src, (
        "worker/executor.py 는 AccountSnapshot 페이로드만 사용해야 함."
    )
    assert "from hydra.db.session import" not in src


def test_executor_source_imports_account_snapshot():
    import worker.executor as ex
    src = inspect.getsource(ex)
    assert "AccountSnapshot" in src
