"""CORS 미들웨어 — env 로 주입된 origin 만 허용."""
import importlib
import os

from fastapi.testclient import TestClient


def _client_with_origins(origins: str) -> TestClient:
    """CORS_ALLOWED_ORIGINS env 를 주고 앱을 다시 로드해 TestClient 반환."""
    os.environ["CORS_ALLOWED_ORIGINS"] = origins
    import hydra.web.app as app_mod
    importlib.reload(app_mod)
    return TestClient(app_mod.app)


def test_cors_allows_configured_origin():
    client = _client_with_origins("https://hydra-prod.duckdns.org,http://localhost:5173")
    resp = client.options(
        "/api/tasks/list",
        headers={
            "Origin": "https://hydra-prod.duckdns.org",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "https://hydra-prod.duckdns.org"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_blocks_random_origin():
    client = _client_with_origins("https://hydra-prod.duckdns.org")
    resp = client.options(
        "/api/tasks/list",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    # 거절되거나 (Starlette 은 400) allow-origin 헤더에 evil 이 없어야 함
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"
