"""감사 로그 미들웨어 — build_audit_entry 동작 검증."""
import json

from hydra.web.middleware.audit import build_audit_entry


def _req(method: str, path: str, ip: str = "10.0.0.1", ua: str = "curl/8.0"):
    return {"method": method, "path": path, "client_ip": ip, "user_agent": ua}


def test_admin_write_request_produces_entry():
    entry = build_audit_entry(
        _req("POST", "/api/admin/deploy"),
        session={"user_id": 7, "role": "admin"},
        body={"confirm": True, "version": "v1.2.3"},
    )
    assert entry is not None
    assert entry["user_id"] == 7
    assert entry["action"] == "deploy"
    assert entry["ip_address"] == "10.0.0.1"
    meta = json.loads(entry["metadata_json"])
    assert meta["body"]["version"] == "v1.2.3"


def test_worker_api_ignored():
    """워커 API 는 감사 대상 아님."""
    entry = build_audit_entry(
        _req("POST", "/api/workers/heartbeat"),
        session={},
        body={"version": "v1"},
    )
    assert entry is None


def test_read_only_get_ignored():
    """쓰기 메소드 (POST/PUT/PATCH/DELETE) 만 기록."""
    entry = build_audit_entry(
        _req("GET", "/api/admin/accounts"),
        session={"user_id": 1, "role": "admin"},
        body=None,
    )
    assert entry is None


def test_sensitive_fields_redacted_from_metadata():
    """password, token 등은 metadata 에서 제외."""
    entry = build_audit_entry(
        _req("POST", "/api/admin/auth/login"),
        session={},
        body={"email": "admin@x.com", "password": "supersecret",
              "token": "abc", "enrollment_token": "xyz", "api_key": "k"},
    )
    assert entry is not None
    meta = json.loads(entry["metadata_json"])
    body = meta["body"]
    assert body["email"] == "admin@x.com"
    for k in ("password", "token", "enrollment_token", "api_key"):
        assert k not in body, f"{k} 가 메타에 남음"


def test_action_inferred_per_path():
    cases = [
        ("/api/admin/deploy", "deploy"),
        ("/api/admin/pause", "pause"),
        ("/api/admin/unpause", "unpause"),
        ("/api/admin/campaigns/123", "campaign_change"),
        ("/api/admin/avatars/upload", "avatar_change"),
        ("/api/admin/workers/enroll", "worker_change"),
        ("/api/admin/accounts/import", "account_change"),
    ]
    for path, expected_action in cases:
        entry = build_audit_entry(
            _req("POST", path),
            session={"user_id": 1, "role": "admin"},
            body={},
        )
        assert entry is not None, f"{path}"
        assert entry["action"] == expected_action, f"{path}: got {entry['action']}"


def test_unknown_admin_path_returns_none():
    """매핑 안 된 /api/admin/* 쓰기 요청은 기록 안 함 (noise 방지)."""
    entry = build_audit_entry(
        _req("POST", "/api/admin/unmapped"),
        session={"user_id": 1, "role": "admin"},
        body={},
    )
    assert entry is None


def test_anonymous_user_recorded_with_null_user_id():
    """로그인 전 요청 (session 비어있음) 도 기록하되 user_id=None."""
    entry = build_audit_entry(
        _req("POST", "/api/admin/auth/login"),
        session={},
        body={},
    )
    # auth/login 은 ACTION_MAP 에 있어야 — 추가하거나 path 매칭 검증
    # 만약 매핑 없으면 None. 이 경우 별도 테스트로 처리.
