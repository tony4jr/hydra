# 프로필 생성 + 세션 전 IP 로테이션 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AdsPower 프로필을 페르소나 device_hint 기반 "찐 사람 번들"로 생성하고, 브라우저 세션 직전에 cross-account 30분 룰을 강제하는 IP 로테이션 훅을 연결한다.

**Architecture:** 지문 번들은 Server 에서 순수 함수로 계산해 태스크 페이로드에 동봉 → Worker 가 로컬 AdsPower API 호출. 세션 시작 시 `ensure_safe_ip()` 훅이 IP 조회 → `ip_log` 조회로 다른 계정 충돌 확인 → 필요 시 `rotate_and_verify()` (즉시 재시도 3회) 실행 → 실패 시 `IPRotationFailed` 전파 후 executor 가 태스크 재스케줄.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, FastAPI, Alembic, pytest, asyncio, httpx, AdsPower Local API, ADB.

**Spec:** `docs/superpowers/specs/2026-04-18-profile-creation-and-ip-rotation-design.md`

---

## 파일 구조

### Create

| 파일 | 책임 |
|---|---|
| `hydra/browser/fingerprint_bundle.py` | `build_fingerprint_payload(device_hint)` 순수 함수 + GPU/폰트/해상도 풀 상수 |
| `hydra/browser/adspower_errors.py` | `AdsPowerAPIError`, `AdsPowerQuotaExceeded` 예외 클래스 |
| `tests/test_fingerprint_bundle.py` | 번들 분포 · OS↔GPU 일치 · 필수 필드 검증 |
| `tests/test_ip_rotation_safety.py` | `check_ip_available` / `ensure_safe_ip` / `rotate_and_verify` |
| `tests/test_account_profile_history.py` | 히스토리 기록 · UNIQUE 위반 · 폐기→재생성 |
| `tests/test_create_profile_flow.py` | CSV → 페르소나 → 태스크 → 후처리 통합 |
| `alembic/versions/abc1_profile_history.py` | UNIQUE 부분 인덱스 + `account_profile_history` 테이블 |

### Modify

| 파일 | 변경 요약 |
|---|---|
| `hydra/db/models.py` | `AccountProfileHistory` 모델 추가 |
| `hydra/core/enums.py` | `TaskType.CREATE_PROFILE`, `RETIRE_PROFILE` 추가 |
| `hydra/core/config.py` | 8개 env var 추가 |
| `hydra/infra/ip.py` | `check_ip_available` 시그니처 변경 + `ensure_safe_ip` + `rotate_and_verify` + `IPRotationFailed` |
| `hydra/browser/adspower.py` | `create_profile` 확장 (fingerprint_config dict 수용) |
| `hydra/accounts/manager.py` | `create_adspower_profile` 히스토리 기록 + `retire_profile` 추가 |
| `hydra/web/routes/accounts.py` | `batch_setup` 과 CSV 임포트 플로우에서 `create_profile` 태스크 큐잉 |
| `hydra/api/tasks.py` | `complete_task` 에 `create_profile` / `retire_profile` 분기 |
| `hydra/core/executor.py` | `IPRotationFailed` 캐치 → 태스크 재스케줄 |
| `worker/executor.py` | `create_profile`, `retire_profile` 핸들러 추가 |
| `worker/session.py` | `rotate_ip` 직접 호출 제거 → `ensure_safe_ip` 로 대체 |

---

## Task 1: TaskType enum 확장 + IP 로테이션 예외 클래스

**Files:**
- Modify: `hydra/core/enums.py` (TaskType 확장)
- Create: `hydra/infra/ip_errors.py` (IPRotationFailed 전용 파일)

**Rationale:** 이후 모든 태스크가 이 심볼들에 의존하므로 먼저 도입.

- [ ] **Step 1: Write the failing test**

Create `tests/test_new_enums_and_errors.py`:

```python
def test_task_type_has_create_profile():
    from hydra.core.enums import TaskType
    assert TaskType.CREATE_PROFILE == "create_profile"
    assert TaskType.RETIRE_PROFILE == "retire_profile"


def test_ip_rotation_failed_is_runtime_error():
    from hydra.infra.ip_errors import IPRotationFailed
    assert issubclass(IPRotationFailed, RuntimeError)
    err = IPRotationFailed("test")
    assert str(err) == "test"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_new_enums_and_errors.py -v
```
Expected: FAIL (AttributeError for CREATE_PROFILE, ModuleNotFoundError for ip_errors).

- [ ] **Step 3: Implement**

Edit `hydra/core/enums.py`, in `class TaskType(StrEnum)` block (around line 188-197) add two members before closing:

```python
class TaskType(StrEnum):
    COMMENT = "comment"
    REPLY = "reply"
    LIKE = "like"
    LIKE_BOOST = "like_boost"
    SUBSCRIBE = "subscribe"
    WARMUP = "warmup"
    GHOST_CHECK = "ghost_check"
    PROFILE_SETUP = "profile_setup"
    CREATE_PROFILE = "create_profile"
    RETIRE_PROFILE = "retire_profile"
```

Create `hydra/infra/ip_errors.py`:

```python
"""IP rotation related exceptions."""


class IPRotationFailed(RuntimeError):
    """Raised when `rotate_and_verify` fails all attempts.
    
    The executor catches this to reschedule the task, rather than marking
    it failed immediately.
    """
    pass


class ADBDeviceNotFound(RuntimeError):
    """Raised when the worker's ADB device is not connected."""
    pass
```

- [ ] **Step 4: Run tests, expect pass**

```
pytest tests/test_new_enums_and_errors.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hydra/core/enums.py hydra/infra/ip_errors.py tests/test_new_enums_and_errors.py
git commit -m "feat: add CREATE_PROFILE/RETIRE_PROFILE task types and IP rotation exceptions"
```

---

## Task 2: Fingerprint bundle 상수와 순수 함수

**Files:**
- Create: `hydra/browser/fingerprint_bundle.py`
- Create: `tests/test_fingerprint_bundle.py`

**Rationale:** 외부 의존 없는 순수 함수 — 가장 먼저 완성해야 이후 태스크가 신뢰하고 사용.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_fingerprint_bundle.py`:

```python
import pytest
from collections import Counter
from hydra.browser.fingerprint_bundle import (
    build_fingerprint_payload,
    WINDOWS_GPU_POOL,
    APPLE_GPU_POOL,
    WINDOWS_KO_FONTS,
    MAC_KO_FONTS,
)


REQUIRED_TOP_KEYS = {
    "random_ua", "browser_kernel_config", "screen_resolution",
    "hardware_concurrency", "device_memory",
    "automatic_timezone", "timezone", "language_switch", "language",
    "location_switch", "webrtc",
    "canvas", "webgl_image", "audio", "client_rects",
    "webgl", "webgl_config", "fonts",
    "device_name_switch", "mac_address_config",
    "media_devices", "media_devices_num", "speech_switch", "scan_port_type",
}


@pytest.mark.parametrize("hint", ["windows_heavy", "windows_10_heavy", "mac_heavy", "mixed"])
def test_payload_has_required_top_keys(hint):
    p = build_fingerprint_payload(hint)
    missing = REQUIRED_TOP_KEYS - set(p.keys())
    assert not missing, f"Missing keys: {missing}"


def test_common_constants_are_fixed():
    p = build_fingerprint_payload("windows_heavy")
    assert p["timezone"] == "Asia/Seoul"
    assert p["language"] == ["ko-KR", "ko", "en-US", "en"]
    assert p["webrtc"] == "disabled"
    assert p["device_name_switch"] == "1"
    assert p["mac_address_config"] == {"model": "1"}
    assert p["browser_kernel_config"] == {"version": "ua_auto", "type": "chrome"}


def test_windows_heavy_uses_windows_ua_and_gpu():
    for _ in range(100):
        p = build_fingerprint_payload("windows_heavy")
        os_versions = p["random_ua"]["ua_system_version"]
        for v in os_versions:
            assert v.startswith("Windows"), f"Got non-Windows UA: {v}"
        vendor = p["webgl_config"]["unmasked_vendor"]
        assert "Apple" not in vendor, f"Windows bundle got Apple GPU: {vendor}"


def test_windows_10_heavy_locks_to_windows_10():
    for _ in range(50):
        p = build_fingerprint_payload("windows_10_heavy")
        assert p["random_ua"]["ua_system_version"] == ["Windows 10"]


def test_mac_heavy_uses_mac_ua_and_apple_gpu():
    for _ in range(100):
        p = build_fingerprint_payload("mac_heavy")
        os_versions = p["random_ua"]["ua_system_version"]
        for v in os_versions:
            assert v.startswith("Mac"), f"Got non-Mac UA: {v}"
        vendor = p["webgl_config"]["unmasked_vendor"]
        assert vendor == "Google Inc. (Apple)"
        # Apple GPU renderer pattern
        renderer = p["webgl_config"]["unmasked_renderer"]
        assert "Apple M" in renderer, f"Got non-Apple renderer: {renderer}"


def test_mac_heavy_uses_mac_fonts():
    p = build_fingerprint_payload("mac_heavy")
    assert "Apple SD Gothic Neo" in p["fonts"]
    assert "AppleGothic" in p["fonts"]
    # should not contain Windows-only font
    assert "Malgun Gothic" not in p["fonts"]


def test_windows_heavy_uses_windows_fonts():
    p = build_fingerprint_payload("windows_heavy")
    assert "Malgun Gothic" in p["fonts"]
    assert "Gulim" in p["fonts"]
    assert "Apple SD Gothic Neo" not in p["fonts"]


def test_mixed_rolls_between_windows_and_mac():
    os_kinds = Counter()
    for _ in range(400):
        p = build_fingerprint_payload("mixed")
        os_versions = p["random_ua"]["ua_system_version"]
        if os_versions[0].startswith("Windows"):
            os_kinds["win"] += 1
        elif os_versions[0].startswith("Mac"):
            os_kinds["mac"] += 1
    # 50/50 distribution, allow ±8% slack
    win_ratio = os_kinds["win"] / 400
    assert 0.42 <= win_ratio <= 0.58, f"win ratio {win_ratio} outside 42-58%"


def test_unknown_device_hint_raises():
    with pytest.raises(ValueError):
        build_fingerprint_payload("android_heavy")


def test_screen_resolution_format():
    p = build_fingerprint_payload("windows_heavy")
    # Format: "1920_1080"
    parts = p["screen_resolution"].split("_")
    assert len(parts) == 2
    assert all(x.isdigit() for x in parts)


def test_media_devices_num_within_range():
    for _ in range(50):
        p = build_fingerprint_payload("windows_heavy")
        m = p["media_devices_num"]
        assert 1 <= int(m["audioinput_num"]) <= 2
        assert int(m["videoinput_num"]) == 1
        assert 1 <= int(m["audiooutput_num"]) <= 2


def test_gpu_pools_are_nonempty_and_weighted():
    assert len(WINDOWS_GPU_POOL) >= 5
    assert len(APPLE_GPU_POOL) >= 3
    # each entry is (vendor, renderer, weight)
    for entry in WINDOWS_GPU_POOL + APPLE_GPU_POOL:
        assert len(entry) == 3
        vendor, renderer, weight = entry
        assert isinstance(vendor, str) and vendor
        assert isinstance(renderer, str) and renderer
        assert isinstance(weight, int) and weight > 0


def test_hardware_concurrency_is_string_digit():
    # AdsPower expects string values from enum "2"/"4"/"6"/"8"/"16"
    p = build_fingerprint_payload("windows_heavy")
    assert p["hardware_concurrency"] in {"2", "4", "6", "8", "16"}


def test_device_memory_max_is_8():
    for _ in range(30):
        p = build_fingerprint_payload("mac_heavy")
        assert p["device_memory"] in {"2", "4", "6", "8"}


def test_webgl_config_has_webgpu():
    p = build_fingerprint_payload("windows_heavy")
    assert p["webgl"] == "2"
    assert "webgpu" in p["webgl_config"]
    assert p["webgl_config"]["webgpu"] == {"webgpu_switch": "1"}
```

- [ ] **Step 2: Run tests, expect fail (module not found)**

```
pytest tests/test_fingerprint_bundle.py -v
```

- [ ] **Step 3: Implement**

Create `hydra/browser/fingerprint_bundle.py`:

```python
"""페르소나 device_hint 기반 AdsPower fingerprint_config 번들 생성.

찐 사람다움을 위해 OS↔GPU↔폰트↔해상도↔코어 가 현실적 조합으로 묶이도록
가중 랜덤 선택. 매 호출이 독립적이며 외부 상태 없음 (순수 함수).
"""

import random

# ─── GPU pools (vendor, renderer, weight) ────────────────────────────

WINDOWS_GPU_POOL = [
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)", 25),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)", 20),
    ("Google Inc. (Intel)",
     "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)", 15),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)", 15),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)", 10),
    ("Google Inc. (AMD)",
     "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)", 10),
    ("Google Inc. (NVIDIA)",
     "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)", 5),
]

APPLE_GPU_POOL = [
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)", 30),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)", 35),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M3, Unspecified Version)", 25),
    ("Google Inc. (Apple)",
     "ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)", 10),
]

# ─── Font lists ──────────────────────────────────────────────────────

WINDOWS_KO_FONTS = [
    "Malgun Gothic", "Malgun Gothic Semilight",
    "Gulim", "GulimChe", "Dotum", "DotumChe",
    "Batang", "BatangChe", "Gungsuh", "GungsuhChe",
    "Arial", "Arial Black", "Calibri", "Cambria", "Consolas",
    "Courier New", "Georgia", "Impact", "Segoe UI",
    "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
]

MAC_KO_FONTS = [
    "Apple SD Gothic Neo", "AppleGothic", "AppleMyungjo", "PilGi",
    "Apple Color Emoji", "Apple Symbols",
    "Helvetica", "Helvetica Neue", "Lucida Grande",
    "Menlo", "Monaco", "SF Pro", "Times New Roman", "Arial",
]

# ─── Common (all bundles) ────────────────────────────────────────────

COMMON_FP = {
    "browser_kernel_config": {"version": "ua_auto", "type": "chrome"},
    "automatic_timezone": "0",
    "timezone": "Asia/Seoul",
    "language_switch": "0",
    "language": ["ko-KR", "ko", "en-US", "en"],
    "location_switch": "1",
    "webrtc": "disabled",
    "canvas": "1",
    "webgl_image": "1",
    "audio": "1",
    "client_rects": "1",
    "webgl": "2",
    "device_name_switch": "1",
    "mac_address_config": {"model": "1"},
    "media_devices": "2",
    "speech_switch": "1",
    "scan_port_type": "1",
}


def _weighted_pick(pool):
    """Pick one (vendor, renderer) from a (vendor, renderer, weight) pool."""
    total = sum(w for _, _, w in pool)
    r = random.uniform(0, total)
    acc = 0
    for vendor, renderer, weight in pool:
        acc += weight
        if r <= acc:
            return vendor, renderer
    vendor, renderer, _ = pool[-1]
    return vendor, renderer


def _random_media_counts():
    return {
        "audioinput_num": str(random.randint(1, 2)),
        "videoinput_num": "1",
        "audiooutput_num": str(random.randint(1, 2)),
    }


def _weighted_choice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]


def _build_windows_heavy() -> dict:
    ua_versions = _weighted_choice(
        [["Windows 10"], ["Windows 11"]], [50, 50]
    )
    vendor, renderer = _weighted_pick(WINDOWS_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ua_versions},
        "screen_resolution": _weighted_choice(
            ["1920_1080", "2560_1440", "1366_768"], [55, 25, 20]
        ),
        "hardware_concurrency": _weighted_choice(["4", "6", "8"], [20, 30, 50]),
        "device_memory": _weighted_choice(["4", "8"], [30, 70]),
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(WINDOWS_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def _build_windows_10_heavy() -> dict:
    vendor, renderer = _weighted_pick(WINDOWS_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ["Windows 10"]},
        "screen_resolution": _weighted_choice(
            ["1920_1080", "1366_768"], [70, 30]
        ),
        "hardware_concurrency": _weighted_choice(["2", "4"], [30, 70]),
        "device_memory": _weighted_choice(["4", "8"], [50, 50]),
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(WINDOWS_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def _build_mac_heavy() -> dict:
    ua_versions = _weighted_choice(
        [["Mac OS X 14"], ["Mac OS X 15"]], [40, 60]
    )
    vendor, renderer = _weighted_pick(APPLE_GPU_POOL)
    return {
        **COMMON_FP,
        "random_ua": {"ua_system_version": ua_versions},
        "screen_resolution": _weighted_choice(
            ["1440_900", "1680_1050", "2560_1440", "2880_1800"],
            [25, 20, 25, 30],
        ),
        "hardware_concurrency": _weighted_choice(["8", "16"], [60, 40]),
        "device_memory": "8",
        "webgl_config": {
            "unmasked_vendor": vendor,
            "unmasked_renderer": renderer,
            "webgpu": {"webgpu_switch": "1"},
        },
        "fonts": list(MAC_KO_FONTS),
        "media_devices_num": _random_media_counts(),
    }


def build_fingerprint_payload(device_hint: str) -> dict:
    """Build AdsPower fingerprint_config dict from a persona device_hint.

    Valid hints: "windows_heavy", "windows_10_heavy", "mac_heavy", "mixed".
    """
    if device_hint == "windows_heavy":
        return _build_windows_heavy()
    if device_hint == "windows_10_heavy":
        return _build_windows_10_heavy()
    if device_hint == "mac_heavy":
        return _build_mac_heavy()
    if device_hint == "mixed":
        return random.choice([_build_windows_heavy, _build_mac_heavy])()
    raise ValueError(f"Unknown device_hint: {device_hint}")
```

- [ ] **Step 4: Run tests, expect all pass**

```
pytest tests/test_fingerprint_bundle.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/browser/fingerprint_bundle.py tests/test_fingerprint_bundle.py
git commit -m "feat: add device_hint → AdsPower fingerprint_config bundle builder"
```

---

## Task 3: `AccountProfileHistory` 모델 + UNIQUE 제약 Alembic 마이그레이션

**Files:**
- Modify: `hydra/db/models.py` (append new model)
- Create: `alembic/versions/<new_rev>_profile_history.py`
- Create: `tests/test_account_profile_history.py`

**Rationale:** 이후 모든 생성/폐기 로직이 이 테이블에 쓰므로 먼저 정립.

- [ ] **Step 1: Write the failing test**

Create `tests/test_account_profile_history.py`:

```python
import json
import pytest
from datetime import datetime, UTC, timedelta
from sqlalchemy.exc import IntegrityError


def test_profile_history_row_can_be_inserted(db_session):
    from hydra.db.models import Account, AccountProfileHistory
    acc = Account(gmail="a@gmail.com", password="pw", status="registered")
    db_session.add(acc)
    db_session.flush()

    h = AccountProfileHistory(
        account_id=acc.id,
        worker_id=None,
        adspower_profile_id="k1bim9ga",
        fingerprint_snapshot=json.dumps({"any": "json"}),
        created_source="auto",
        device_hint="windows_heavy",
    )
    db_session.add(h)
    db_session.commit()

    got = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).one()
    assert got.adspower_profile_id == "k1bim9ga"
    assert got.retired_at is None
    assert got.created_source == "auto"


def test_adspower_profile_id_unique_constraint(db_session):
    """Two accounts cannot share the same AdsPower profile_id."""
    from hydra.db.models import Account
    a1 = Account(gmail="one@g.com", password="x",
                 adspower_profile_id="dup123", status="profile_set")
    a2 = Account(gmail="two@g.com", password="y",
                 adspower_profile_id="dup123", status="profile_set")
    db_session.add(a1)
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_null_adspower_profile_id_allows_multiple(db_session):
    """NULL adspower_profile_id must be allowed for many accounts."""
    from hydra.db.models import Account
    a1 = Account(gmail="n1@g.com", password="x", status="registered")
    a2 = Account(gmail="n2@g.com", password="y", status="registered")
    db_session.add(a1)
    db_session.add(a2)
    db_session.commit()  # should NOT raise


def test_retire_then_recreate_keeps_history(db_session):
    """Retiring a profile then creating a new one leaves two history rows."""
    from hydra.db.models import Account, AccountProfileHistory
    acc = Account(gmail="r@g.com", password="x",
                  adspower_profile_id="old", status="profile_set")
    db_session.add(acc)
    db_session.flush()
    old = AccountProfileHistory(
        account_id=acc.id, adspower_profile_id="old",
        created_source="auto", device_hint="windows_heavy",
    )
    db_session.add(old)
    db_session.commit()

    # retire
    old.retired_at = datetime.now(UTC)
    old.retire_reason = "ghost"
    acc.adspower_profile_id = None
    db_session.commit()

    # recreate
    acc.adspower_profile_id = "new"
    new = AccountProfileHistory(
        account_id=acc.id, adspower_profile_id="new",
        created_source="auto", device_hint="windows_heavy",
    )
    db_session.add(new)
    db_session.commit()

    rows = (db_session.query(AccountProfileHistory)
            .filter_by(account_id=acc.id).order_by(AccountProfileHistory.id).all())
    assert len(rows) == 2
    assert rows[0].retired_at is not None
    assert rows[1].retired_at is None
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_account_profile_history.py -v
```

- [ ] **Step 3: Add `AccountProfileHistory` model**

Append to `hydra/db/models.py` just before `class Worker` (or at end of file, any stable spot):

```python
class AccountProfileHistory(Base):
    __tablename__ = "account_profile_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)
    adspower_profile_id = Column(String, nullable=False)
    fingerprint_snapshot = Column(Text)  # JSON
    created_source = Column(String, nullable=False, default="auto")  # auto | manual_mapped
    device_hint = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    retired_at = Column(DateTime)
    retire_reason = Column(String)

    __table_args__ = (
        Index("idx_profhist_account", "account_id"),
        Index("idx_profhist_active", "account_id", "retired_at"),
    )
```

And add UNIQUE partial index for `accounts.adspower_profile_id` — the simplest approach is to use `UniqueConstraint` with SQLAlchemy, but since we need partial (NULL allowed multiple), use Alembic-level index. For now, **add at Python level a `UniqueConstraint` that works in SQLite** (SQLite treats multiple NULLs as distinct by default for UNIQUE constraints — this is fine).

Edit `Account.__table_args__` or add if missing. Search for end of `Account` class definition (around line 60-80) and add:

```python
    __table_args__ = (
        Index("idx_accounts_status", "status"),
        Index("idx_accounts_warmup", "warmup_group", "status"),
        UniqueConstraint("adspower_profile_id", name="uq_accounts_adspower_profile_id"),
    )
```

If `Account.__table_args__` already exists, merge the new `UniqueConstraint` into the existing tuple.

- [ ] **Step 4: Run tests**

```
pytest tests/test_account_profile_history.py -v
```
Expected: PASS. (SQLite allows multiple NULLs even with plain UNIQUE, so partial index not strictly needed for test; Postgres migration will use partial index via Alembic.)

- [ ] **Step 5: Alembic migration**

Generate a new revision:

```bash
alembic revision -m "add account_profile_history and adspower uq"
```

Edit the generated file (path like `alembic/versions/<hash>_add_account_profile_history_and_adspower_uq.py`) to have these `upgrade` / `downgrade` bodies:

```python
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        "account_profile_history",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("worker_id", sa.Integer(), sa.ForeignKey("workers.id"), nullable=True),
        sa.Column("adspower_profile_id", sa.String(), nullable=False),
        sa.Column("fingerprint_snapshot", sa.Text(), nullable=True),
        sa.Column("created_source", sa.String(), nullable=False, server_default="auto"),
        sa.Column("device_hint", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("retired_at", sa.DateTime(), nullable=True),
        sa.Column("retire_reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_profhist_account", "account_profile_history", ["account_id"])
    op.create_index("idx_profhist_active", "account_profile_history",
                    ["account_id", "retired_at"])

    # Backfill existing rows: any account with adspower_profile_id gets a history row.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, adspower_profile_id FROM accounts "
        "WHERE adspower_profile_id IS NOT NULL AND adspower_profile_id != ''"
    )).fetchall()
    for acc_id, pid in rows:
        conn.execute(sa.text(
            "INSERT INTO account_profile_history "
            "(account_id, adspower_profile_id, created_source, created_at) "
            "VALUES (:a, :p, 'manual_mapped', CURRENT_TIMESTAMP)"
        ), {"a": acc_id, "p": pid})

    # Add UNIQUE on accounts.adspower_profile_id. On SQLite / Postgres both
    # treat NULL as distinct for UNIQUE, so partial index not strictly needed.
    with op.batch_alter_table("accounts") as batch:
        batch.create_unique_constraint(
            "uq_accounts_adspower_profile_id", ["adspower_profile_id"]
        )


def downgrade():
    with op.batch_alter_table("accounts") as batch:
        batch.drop_constraint("uq_accounts_adspower_profile_id", type_="unique")
    op.drop_index("idx_profhist_active", table_name="account_profile_history")
    op.drop_index("idx_profhist_account", table_name="account_profile_history")
    op.drop_table("account_profile_history")
```

Apply:

```bash
alembic upgrade head
```
Expected output: `INFO  [alembic.runtime.migration] Running upgrade ...`

Verify:

```bash
sqlite3 data/hydra.db ".schema account_profile_history"
sqlite3 data/hydra.db "SELECT COUNT(*) FROM account_profile_history;"
```
Expected: schema printed, count = 0 (no existing profile_ids in data).

- [ ] **Step 6: Commit**

```bash
git add hydra/db/models.py alembic/versions/*profile_history*.py tests/test_account_profile_history.py
git commit -m "feat: add AccountProfileHistory table and UNIQUE on adspower_profile_id"
```

---

## Task 4: Config env vars

**Files:**
- Modify: `hydra/core/config.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_new_enums_and_errors.py`:

```python
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
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_new_enums_and_errors.py::test_new_config_defaults -v
```

- [ ] **Step 3: Implement**

Edit `hydra/core/config.py`. Inside `class Settings(BaseSettings)` (after the `backup_retention_days` line, before `# === Worker ===`):

```python
    # === Fingerprint / Profile ===
    adspower_group_id: str = "0"
    adspower_profile_quota: int = 100
    enable_fingerprint_bundle: bool = True

    # === IP rotation ===
    ip_rotation_cooldown_minutes: int = 30
    ip_rotation_max_attempts: int = 3
    ip_rotation_task_retry_max: int = 5
    ip_rotation_reschedule_min: int = 5
    ip_rotation_reschedule_max: int = 10
```

- [ ] **Step 4: Run, expect pass**

```
pytest tests/test_new_enums_and_errors.py::test_new_config_defaults -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/config.py tests/test_new_enums_and_errors.py
git commit -m "feat: add config env vars for fingerprint bundle and IP rotation"
```

---

## Task 5: `check_ip_available` — cross-account 규칙으로 시그니처 변경

**Files:**
- Modify: `hydra/infra/ip.py` (signature change)
- Create: `tests/test_ip_rotation_safety.py`
- 사용처 업데이트 (`hydra/accounts/warmup_runner.py`, 기타 grep)

**Breaking change:** 기존 `check_ip_available(db, ip, cooldown_minutes)` → `check_ip_available(db, ip, account_id, cooldown_minutes=30)`. `rotate_ip()` 내부 호출자도 업데이트 필요.

- [ ] **Step 1: Write failing test**

Create `tests/test_ip_rotation_safety.py`:

```python
from datetime import datetime, UTC, timedelta


def _add_account(db, gmail):
    from hydra.db.models import Account
    a = Account(gmail=gmail, password="x", status="active")
    db.add(a)
    db.flush()
    return a


def _add_ip_log(db, account_id, ip, minutes_ago=0):
    from hydra.db.models import IpLog
    log = IpLog(
        account_id=account_id,
        ip_address=ip,
        device_id="test",
        started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    db.add(log)
    db.flush()
    return log


def test_check_ip_available_true_when_no_log(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    assert check_ip_available(db_session, "1.2.3.4", a.id) is True


def test_check_ip_available_true_for_same_account(db_session):
    """Same account re-using same IP within cooldown is OK (real users do this)."""
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=5)
    assert check_ip_available(db_session, "1.2.3.4", a.id) is True


def test_check_ip_available_false_for_other_account_within_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=10)
    # B cannot use the IP until 30 min passes
    assert check_ip_available(db_session, "1.2.3.4", b.id) is False


def test_check_ip_available_true_for_other_account_after_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=31)
    assert check_ip_available(db_session, "1.2.3.4", b.id) is True


def test_check_ip_available_custom_cooldown(db_session):
    from hydra.infra.ip import check_ip_available
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "1.2.3.4", minutes_ago=10)
    assert check_ip_available(db_session, "1.2.3.4", b.id,
                              cooldown_minutes=5) is True
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_ip_rotation_safety.py -v
```
Expected: FAIL — signature mismatch (old `check_ip_available` takes `cooldown_minutes=30` as second positional arg).

- [ ] **Step 3: Update implementation**

Edit `hydra/infra/ip.py`. Replace `check_ip_available` function (around lines 96-110) with:

```python
def check_ip_available(
    db: Session,
    ip_address: str,
    account_id: int,
    cooldown_minutes: int = 30,
) -> bool:
    """Check if another account used this IP within the cooldown window.
    
    Same account re-using its own IP is allowed (real humans reconnect to the
    same IP naturally). Only cross-account reuse within the window blocks.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    conflict = (
        db.query(IpLog)
        .filter(
            IpLog.ip_address == ip_address,
            IpLog.started_at >= cutoff,
            IpLog.account_id != account_id,
        )
        .first()
    )
    return conflict is None
```

- [ ] **Step 4: Find callers and update**

```bash
grep -rn "check_ip_available" hydra/ worker/ tests/ --include="*.py"
```

Update any existing caller to pass `account_id`. (Current audit: only tests and spec docs reference it; code callers don't yet exist outside of this refactor. If a caller exists that doesn't pass account_id, fix it to pass the relevant account's id.)

- [ ] **Step 5: Run tests**

```
pytest tests/test_ip_rotation_safety.py -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hydra/infra/ip.py tests/test_ip_rotation_safety.py
git commit -m "refactor(ip): check_ip_available now filters by other accounts within cooldown"
```

---

## Task 6: `rotate_and_verify` — 즉시 재시도 3회 + 검증

**Files:**
- Modify: `hydra/infra/ip.py` (add new function)
- Modify: `tests/test_ip_rotation_safety.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_ip_rotation_safety.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_rotate_and_verify_succeeds_on_first_attempt(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod

    calls = []

    async def fake_shell(device_id, cmd):
        calls.append(cmd)
        return ""

    async def fake_get_ip(device_id):
        # previous IP 1.1.1.1, new IP 2.2.2.2 after first toggle
        return "2.2.2.2" if len(calls) >= 2 else "1.1.1.1"

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    a = _add_account(db_session, "a@g.com")
    result = await ip_mod.rotate_and_verify(db_session, "DEV", a.id)
    assert result == "2.2.2.2"


@pytest.mark.asyncio
async def test_rotate_and_verify_retries_on_conflict(db_session, monkeypatch):
    """First attempt returns conflicted IP, second attempt succeeds."""
    from hydra.infra import ip as ip_mod

    toggles = {"n": 0}

    async def fake_shell(device_id, cmd):
        if "enable" in cmd:
            toggles["n"] += 1
        return ""

    sequence = iter(["1.1.1.1", "9.9.9.9", "2.2.2.2"])  # prev, conflict, safe

    async def fake_get_ip(device_id):
        return next(sequence)

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    # account A owns 9.9.9.9 currently → account B must NOT get 9.9.9.9
    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    _add_ip_log(db_session, a.id, "9.9.9.9", minutes_ago=1)
    db_session.commit()

    result = await ip_mod.rotate_and_verify(db_session, "DEV", b.id)
    assert result == "2.2.2.2"
    assert toggles["n"] == 2  # two enable toggles


@pytest.mark.asyncio
async def test_rotate_and_verify_raises_after_three_failures(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod
    from hydra.infra.ip_errors import IPRotationFailed

    async def fake_shell(device_id, cmd):
        return ""

    async def fake_get_ip(device_id):
        # always same IP — never changes
        return "1.1.1.1"

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    # fake telegram to avoid network
    import hydra.infra.telegram as telegram
    monkeypatch.setattr(telegram, "warning", lambda *a, **k: None)

    a = _add_account(db_session, "a@g.com")

    with pytest.raises(IPRotationFailed):
        await ip_mod.rotate_and_verify(db_session, "DEV", a.id)
```

Also ensure pytest-asyncio is configured. Check `pytest.ini` / `pyproject.toml` / `conftest.py` for `asyncio_mode`. If not present, add to `tests/conftest.py`:

```python
import pytest_asyncio  # noqa — ensures plugin is imported
pytest_plugins = ("pytest_asyncio",)
```

And if pytest-asyncio is not installed, add:

```bash
uv add pytest-asyncio  # or: pip install pytest-asyncio
```

- [ ] **Step 2: Run, expect fail (function missing)**

```
pytest tests/test_ip_rotation_safety.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/infra/ip.py`. Add imports near top:

```python
from hydra.infra.ip_errors import IPRotationFailed, ADBDeviceNotFound
from hydra.core.config import settings
```

Add function (place after `check_ip_available`):

```python
async def rotate_and_verify(db: Session, device_id: str, account_id: int) -> str:
    """Toggle mobile data off/on up to N times until a safe IP is obtained.
    
    "Safe" = not used by another account within `settings.ip_rotation_cooldown_minutes`.
    Raises `IPRotationFailed` when all attempts exhausted.
    """
    previous_ip = await _get_current_ip(device_id)

    max_attempts = settings.ip_rotation_max_attempts
    for attempt in range(1, max_attempts + 1):
        log.info(f"IP rotation attempt {attempt}/{max_attempts} (prev: {previous_ip})")

        await _adb_shell(device_id, "svc data disable")
        await asyncio.sleep(5)
        await _adb_shell(device_id, "svc data enable")
        await asyncio.sleep(15)

        try:
            new_ip = await _get_current_ip(device_id)
        except Exception as e:
            log.warning(f"IP check failed (attempt {attempt}): {e}")
            continue

        if not new_ip or new_ip == previous_ip:
            log.warning(f"Attempt {attempt}: IP unchanged ({new_ip})")
            continue

        if check_ip_available(db, new_ip, account_id,
                               cooldown_minutes=settings.ip_rotation_cooldown_minutes):
            log.info(f"IP rotated safely: {previous_ip} → {new_ip}")
            return new_ip

        log.warning(f"Attempt {attempt}: new IP {new_ip} still conflicts with another account")
        previous_ip = new_ip

    from hydra.infra import telegram
    telegram.warning(
        f"⚠️ IP 로테이션 {max_attempts}회 실패 — device={device_id}, account_id={account_id}"
    )
    raise IPRotationFailed(
        f"Failed to obtain safe IP after {max_attempts} attempts (device={device_id})"
    )
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_ip_rotation_safety.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hydra/infra/ip.py tests/test_ip_rotation_safety.py tests/conftest.py
git commit -m "feat(ip): rotate_and_verify with immediate retries and cross-account check"
```

---

## Task 7: `ensure_safe_ip` 훅

**Files:**
- Modify: `hydra/infra/ip.py` (new function)
- Modify: `tests/test_ip_rotation_safety.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_ip_rotation_safety.py`:

```python
import json as _json


@pytest.mark.asyncio
async def test_ensure_safe_ip_returns_iplog_when_current_ip_safe(db_session, monkeypatch):
    """No conflict → record current IP in ip_log and return without rotating."""
    from hydra.infra import ip as ip_mod
    from hydra.db.models import Worker

    a = _add_account(db_session, "a@g.com")
    w = Worker(name="w1", token_hash="h", status="online",
               ip_config=_json.dumps({"adb_device_id": "DEV"}))
    db_session.add(w)
    db_session.commit()

    async def fake_get_ip(device_id):
        return "1.1.1.1"

    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)

    log = await ip_mod.ensure_safe_ip(db_session, a, w)
    assert log.ip_address == "1.1.1.1"
    assert log.account_id == a.id
    assert log.device_id == "DEV"


@pytest.mark.asyncio
async def test_ensure_safe_ip_rotates_on_conflict(db_session, monkeypatch):
    from hydra.infra import ip as ip_mod
    from hydra.db.models import Worker

    a = _add_account(db_session, "a@g.com")
    b = _add_account(db_session, "b@g.com")
    w = Worker(name="w1", token_hash="h", status="online",
               ip_config=_json.dumps({"adb_device_id": "DEV"}))
    db_session.add(w)
    _add_ip_log(db_session, a.id, "1.1.1.1", minutes_ago=2)
    db_session.commit()

    # current = 1.1.1.1 conflicts with A → rotate → get 2.2.2.2
    sequence = iter(["1.1.1.1", "1.1.1.1", "2.2.2.2"])

    async def fake_get_ip(device_id):
        return next(sequence)

    async def fake_shell(*args, **kwargs):
        return ""

    async def fake_sleep(_):
        return None

    monkeypatch.setattr(ip_mod, "_get_current_ip", fake_get_ip)
    monkeypatch.setattr(ip_mod, "_adb_shell", fake_shell)
    monkeypatch.setattr(ip_mod.asyncio, "sleep", fake_sleep)

    log = await ip_mod.ensure_safe_ip(db_session, b, w)
    assert log.ip_address == "2.2.2.2"
    assert log.account_id == b.id


@pytest.mark.asyncio
async def test_ensure_safe_ip_skips_rotation_when_no_device_id(db_session, monkeypatch):
    """If worker has no ADB device configured, log IP but don't rotate."""
    from hydra.infra import ip as ip_mod
    from hydra.db.models import Worker

    a = _add_account(db_session, "a@g.com")
    w = Worker(name="w2", token_hash="h", status="online", ip_config=None)
    db_session.add(w)
    db_session.commit()

    async def fake_external(_=None):
        return "6.6.6.6"

    monkeypatch.setattr(ip_mod, "_get_worker_external_ip", fake_external)

    log = await ip_mod.ensure_safe_ip(db_session, a, w)
    assert log.ip_address == "6.6.6.6"
    assert log.device_id == "none"
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_ip_rotation_safety.py -v -k ensure_safe_ip
```

- [ ] **Step 3: Implement**

Edit `hydra/infra/ip.py`. Add imports at top if not present:

```python
import json
```

Add these functions (after `rotate_and_verify`):

```python
async def _get_worker_external_ip() -> str:
    """Fallback: ask the machine for its own external IP (no ADB)."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://ifconfig.me")
            return resp.text.strip()
    except Exception:
        return "0.0.0.0"


async def ensure_safe_ip(db: Session, account, worker) -> "IpLog":
    """Ensure the session uses an IP not claimed by another account in cooldown.

    1. If worker has no adb_device_id: log current machine external IP, skip rotate.
    2. Query current phone IP via ADB.
    3. If no conflict → log and return.
    4. If conflict → rotate_and_verify → log new IP and return.
    """
    ip_config = {}
    if worker.ip_config:
        try:
            ip_config = json.loads(worker.ip_config)
        except Exception:
            ip_config = {}
    device_id = ip_config.get("adb_device_id")

    if not device_id:
        current_ip = await _get_worker_external_ip()
        return log_ip_usage(db, account.id, current_ip, "none")

    current_ip = await _get_current_ip(device_id)

    if check_ip_available(db, current_ip, account.id,
                          cooldown_minutes=settings.ip_rotation_cooldown_minutes):
        return log_ip_usage(db, account.id, current_ip, device_id)

    new_ip = await rotate_and_verify(db, device_id, account.id)
    return log_ip_usage(db, account.id, new_ip, device_id)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_ip_rotation_safety.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add hydra/infra/ip.py tests/test_ip_rotation_safety.py
git commit -m "feat(ip): add ensure_safe_ip session hook"
```

---

## Task 8: AdsPower 예외 클래스 + `create_profile` 확장

**Files:**
- Create: `hydra/browser/adspower_errors.py`
- Modify: `hydra/browser/adspower.py`
- Create: `tests/test_adspower_client.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_adspower_client.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


def test_adspower_errors_exist():
    from hydra.browser.adspower_errors import AdsPowerAPIError, AdsPowerQuotaExceeded
    assert issubclass(AdsPowerAPIError, RuntimeError)
    assert issubclass(AdsPowerQuotaExceeded, AdsPowerAPIError)


def test_create_profile_accepts_fingerprint_config():
    """create_profile(name, group_id, fingerprint_config=...) forwards the dict."""
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
        # Simulate AdsPower reply containing quota message
        raise RuntimeError("AdsPower error: Account package limit exceeded")

    with patch.object(client, "_post", side_effect=fake_post):
        with pytest.raises(AdsPowerQuotaExceeded):
            client.create_profile(
                name="n", group_id="0",
                fingerprint_config={"timezone": "Asia/Seoul"},
            )
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_adspower_client.py -v
```

- [ ] **Step 3: Implement**

Create `hydra/browser/adspower_errors.py`:

```python
"""AdsPower Local API error hierarchy."""


class AdsPowerAPIError(RuntimeError):
    """Base for any AdsPower Local API failure."""


class AdsPowerQuotaExceeded(AdsPowerAPIError):
    """Profile quota reached — cannot create more."""
```

Edit `hydra/browser/adspower.py`. Replace the existing `create_profile` method:

```python
    def create_profile(
        self,
        name: str,
        group_id: str = "0",
        fingerprint_config: dict | None = None,
        remark: str = "",
    ) -> str:
        """Create a new browser profile. Returns profile ID.
        
        `fingerprint_config` is the AdsPower fingerprint_config dict produced
        by `hydra.browser.fingerprint_bundle.build_fingerprint_payload`.
        """
        from hydra.browser.adspower_errors import (
            AdsPowerAPIError, AdsPowerQuotaExceeded,
        )

        body = {
            "name": name,
            "group_id": group_id,
            "remark": remark,
            "user_proxy_config": {"proxy_soft": "no_proxy"},
            "fingerprint_config": fingerprint_config or {
                "language": ["ko-KR", "ko", "en-US", "en"],
            },
        }

        try:
            data = self._post("/api/v1/user/create", body)
        except RuntimeError as e:
            msg = str(e).lower()
            if any(k in msg for k in ["limit exceeded", "quota", "package limit"]):
                raise AdsPowerQuotaExceeded(str(e)) from e
            raise AdsPowerAPIError(str(e)) from e

        profile_id = data.get("id", "")
        log.info(f"Created AdsPower profile: {name} → {profile_id}")
        return profile_id
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_adspower_client.py -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hydra/browser/adspower.py hydra/browser/adspower_errors.py tests/test_adspower_client.py
git commit -m "feat(adspower): accept fingerprint_config dict, add quota/error types"
```

---

## Task 9: `accounts/manager.py` — history 통합 + `retire_profile`

**Files:**
- Modify: `hydra/accounts/manager.py`
- Modify: `tests/test_account_profile_history.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_account_profile_history.py`:

```python
def test_record_profile_creation_inserts_history(db_session):
    from hydra.db.models import Account, AccountProfileHistory
    from hydra.accounts.manager import record_profile_creation

    acc = Account(gmail="r@g.com", password="x", status="registered")
    db_session.add(acc)
    db_session.commit()

    fp = {"random_ua": {"ua_system_version": ["Windows 11"]}}
    record_profile_creation(
        db_session, acc, profile_id="k1bim9ga", worker_id=None,
        fingerprint_snapshot=fp, device_hint="windows_heavy",
        created_source="auto",
    )

    db_session.refresh(acc)
    assert acc.adspower_profile_id == "k1bim9ga"
    assert acc.status == "profile_set"

    rows = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).all()
    assert len(rows) == 1
    assert rows[0].retired_at is None
    assert rows[0].device_hint == "windows_heavy"


def test_record_profile_creation_refuses_if_already_active(db_session):
    from hydra.db.models import Account
    from hydra.accounts.manager import record_profile_creation

    acc = Account(gmail="r@g.com", password="x",
                  adspower_profile_id="existing", status="profile_set")
    db_session.add(acc)
    db_session.commit()

    import pytest
    with pytest.raises(ValueError, match="already has an active profile"):
        record_profile_creation(
            db_session, acc, profile_id="new",
            worker_id=None, fingerprint_snapshot={}, device_hint="x",
        )


def test_retire_profile_sets_retired_at_and_nulls_account_field(db_session):
    from hydra.db.models import Account, AccountProfileHistory
    from hydra.accounts.manager import record_profile_creation, retire_profile_record

    acc = Account(gmail="r@g.com", password="x", status="registered")
    db_session.add(acc)
    db_session.commit()
    record_profile_creation(
        db_session, acc, profile_id="old", worker_id=None,
        fingerprint_snapshot={}, device_hint="windows_heavy",
    )

    retire_profile_record(db_session, acc, reason="ghost")

    db_session.refresh(acc)
    assert acc.adspower_profile_id is None
    row = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).one()
    assert row.retired_at is not None
    assert row.retire_reason == "ghost"
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_account_profile_history.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/accounts/manager.py`. Add imports at top:

```python
import json
from hydra.db.models import AccountProfileHistory
```

Replace (or add next to) the existing `create_adspower_profile` function:

```python
def record_profile_creation(
    db: Session,
    account: Account,
    *,
    profile_id: str,
    worker_id: int | None,
    fingerprint_snapshot: dict,
    device_hint: str,
    created_source: str = "auto",
) -> AccountProfileHistory:
    """Atomically link an AdsPower profile to an account and record history.

    Raises:
        ValueError: if the account already has an active profile.
    """
    if account.adspower_profile_id:
        raise ValueError(
            f"Account {account.id} ({account.gmail}) already has an active profile: "
            f"{account.adspower_profile_id}"
        )

    account.adspower_profile_id = profile_id
    account.status = AccountStatus.PROFILE_SET

    history = AccountProfileHistory(
        account_id=account.id,
        worker_id=worker_id,
        adspower_profile_id=profile_id,
        fingerprint_snapshot=json.dumps(fingerprint_snapshot, ensure_ascii=False),
        created_source=created_source,
        device_hint=device_hint,
    )
    db.add(history)
    db.commit()
    log.info(f"Profile {profile_id} linked to {account.gmail} (source={created_source})")
    return history


def retire_profile_record(db: Session, account: Account, reason: str):
    """Mark the account's active profile as retired. Idempotent."""
    if not account.adspower_profile_id:
        return
    active = (
        db.query(AccountProfileHistory)
        .filter_by(account_id=account.id, retired_at=None)
        .first()
    )
    if active:
        active.retired_at = datetime.now(timezone.utc)
        active.retire_reason = reason
    account.adspower_profile_id = None
    db.commit()
    log.info(f"Profile retired for {account.gmail} (reason={reason})")
```

Update the old `create_adspower_profile` function to use the new helper AND also call AdsPower:

```python
def create_adspower_profile(
    db: Session,
    account: Account,
    *,
    fingerprint_config: dict | None = None,
    device_hint: str = "windows_heavy",
) -> str:
    """Server-side convenience: create profile synchronously on Worker-less setups.

    In production, prefer queueing a `create_profile` task so a Worker handles
    the AdsPower API call (Worker has the local AdsPower instance).
    """
    from hydra.browser.fingerprint_bundle import build_fingerprint_payload
    name = f"hydra_{account.id}_{account.gmail.split('@')[0]}"
    if fingerprint_config is None:
        fingerprint_config = build_fingerprint_payload(device_hint)

    for attempt in range(3):
        try:
            profile_id = adspower.create_profile(
                name=name,
                group_id=settings.adspower_group_id,
                fingerprint_config=fingerprint_config,
            )
            record_profile_creation(
                db, account,
                profile_id=profile_id, worker_id=None,
                fingerprint_snapshot=fingerprint_config,
                device_hint=device_hint,
            )
            return profile_id
        except Exception as e:
            log.warning(f"AdsPower profile creation attempt {attempt+1} failed: {e}")
            if attempt == 2:
                telegram.warning(f"AdsPower 프로필 생성 실패: {account.gmail}")
                raise
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_account_profile_history.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/accounts/manager.py tests/test_account_profile_history.py
git commit -m "feat(accounts): atomic profile-link + retire with history"
```

---

## Task 10: Worker 핸들러 `create_profile` / `retire_profile`

**Files:**
- Modify: `worker/executor.py`
- Create: `tests/test_worker_profile_handlers.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_worker_profile_handlers.py`:

```python
import json
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_handle_create_profile_returns_profile_id():
    from worker.executor import TaskExecutor
    ex = TaskExecutor()

    task = {
        "task_type": "create_profile",
        "payload": json.dumps({
            "account_id": 1,
            "profile_name": "hydra_1_test",
            "group_id": "0",
            "remark": "test",
            "device_hint": "windows_heavy",
            "fingerprint_payload": {"timezone": "Asia/Seoul"},
        }),
    }

    with patch("worker.executor.adspower") as m:
        m.create_profile.return_value = "gen123"
        result = await ex.execute(task, session=None)

    assert isinstance(result, str)
    data = json.loads(result)
    assert data["profile_id"] == "gen123"


@pytest.mark.asyncio
async def test_handle_create_profile_propagates_quota_error():
    from worker.executor import TaskExecutor
    from hydra.browser.adspower_errors import AdsPowerQuotaExceeded
    ex = TaskExecutor()

    task = {
        "task_type": "create_profile",
        "payload": json.dumps({
            "account_id": 1,
            "profile_name": "n",
            "group_id": "0",
            "fingerprint_payload": {},
        }),
    }

    with patch("worker.executor.adspower") as m:
        m.create_profile.side_effect = AdsPowerQuotaExceeded("limit")
        with pytest.raises(AdsPowerQuotaExceeded):
            await ex.execute(task, session=None)


@pytest.mark.asyncio
async def test_handle_retire_profile_calls_delete():
    from worker.executor import TaskExecutor
    ex = TaskExecutor()

    task = {
        "task_type": "retire_profile",
        "payload": json.dumps({
            "profile_id": "to_delete",
            "reason": "ghost",
        }),
    }

    with patch("worker.executor.adspower") as m:
        result = await ex.execute(task, session=None)
        m.delete_profile.assert_called_once_with("to_delete")

    data = json.loads(result)
    assert data["retired_profile_id"] == "to_delete"
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_worker_profile_handlers.py -v
```

- [ ] **Step 3: Implement**

Edit `worker/executor.py`. Add at top of file:

```python
from hydra.browser.adspower import adspower
```

Inside `TaskExecutor.__init__`, extend the handlers dict:

```python
        self.handlers = {
            "comment": self._handle_comment,
            "reply": self._handle_reply,
            "like": self._handle_like,
            "like_boost": self._handle_like_boost,
            "subscribe": self._handle_subscribe,
            "warmup": self._handle_warmup,
            "ghost_check": self._handle_ghost_check,
            "login": self._handle_login,
            "channel_setup": self._handle_channel_setup,
            "create_profile": self._handle_create_profile,
            "retire_profile": self._handle_retire_profile,
        }
```

Add handler methods anywhere inside the class (e.g., at the bottom):

```python
    async def _handle_create_profile(self, task, payload, session):
        """Create an AdsPower profile with the given fingerprint bundle.

        session is unused — this handler doesn't need a browser.
        """
        name = payload["profile_name"]
        group_id = payload.get("group_id", "0")
        remark = payload.get("remark", "")
        fingerprint_config = payload.get("fingerprint_payload") or {}

        profile_id = adspower.create_profile(
            name=name,
            group_id=group_id,
            fingerprint_config=fingerprint_config,
            remark=remark,
        )
        return json.dumps({
            "profile_id": profile_id,
            "account_id": payload["account_id"],
            "device_hint": payload.get("device_hint"),
        })

    async def _handle_retire_profile(self, task, payload, session):
        profile_id = payload["profile_id"]
        adspower.delete_profile(profile_id)
        return json.dumps({
            "retired_profile_id": profile_id,
            "reason": payload.get("reason", ""),
        })
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_worker_profile_handlers.py -v
```

- [ ] **Step 5: Commit**

```bash
git add worker/executor.py tests/test_worker_profile_handlers.py
git commit -m "feat(worker): add create_profile/retire_profile handlers"
```

---

## Task 11: Server-side `complete_task` 분기

**Files:**
- Modify: `hydra/api/tasks.py` (extend `complete_task`)
- Create: `tests/test_complete_task_profile.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_complete_task_profile.py`:

```python
import json
import pytest


def test_complete_create_profile_success_links_and_records_history(db_session):
    from hydra.db.models import Account, Task, AccountProfileHistory
    from hydra.api.tasks import handle_create_profile_result

    acc = Account(gmail="a@g.com", password="x", status="registered")
    db_session.add(acc)
    db_session.flush()

    payload = {
        "account_id": acc.id,
        "profile_name": "hydra_{}_a".format(acc.id),
        "device_hint": "windows_heavy",
        "fingerprint_payload": {"timezone": "Asia/Seoul"},
    }
    task = Task(
        account_id=acc.id, task_type="create_profile",
        status="pending", payload=json.dumps(payload),
    )
    db_session.add(task)
    db_session.commit()

    result = {"profile_id": "new123", "account_id": acc.id,
              "device_hint": "windows_heavy"}
    handle_create_profile_result(db_session, task, result, worker_id=7)

    db_session.refresh(acc)
    assert acc.adspower_profile_id == "new123"
    assert acc.status == "profile_set"
    rows = db_session.query(AccountProfileHistory).filter_by(account_id=acc.id).all()
    assert len(rows) == 1
    assert rows[0].worker_id == 7
    assert rows[0].adspower_profile_id == "new123"


def test_complete_create_profile_duplicate_queues_retire_task(db_session):
    from hydra.db.models import Account, Task
    from hydra.api.tasks import handle_create_profile_result

    acc = Account(gmail="b@g.com", password="x",
                  adspower_profile_id="already_there", status="profile_set")
    db_session.add(acc)
    db_session.flush()

    task = Task(
        account_id=acc.id, task_type="create_profile", status="pending",
        payload=json.dumps({"account_id": acc.id, "device_hint": "windows_heavy"}),
    )
    db_session.add(task)
    db_session.commit()

    result = {"profile_id": "duplicate", "account_id": acc.id}
    handle_create_profile_result(db_session, task, result, worker_id=3)

    # Retire task should exist for the duplicate
    retire = db_session.query(Task).filter_by(task_type="retire_profile").first()
    assert retire is not None
    retire_payload = json.loads(retire.payload)
    assert retire_payload["profile_id"] == "duplicate"
    assert retire_payload["reason"] == "duplicate_creation"

    # Account still points to the original profile
    db_session.refresh(acc)
    assert acc.adspower_profile_id == "already_there"
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_complete_task_profile.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/api/tasks.py`. Add at top:

```python
import json
from hydra.db.models import AccountProfileHistory
from hydra.accounts.manager import record_profile_creation
```

Add new helper function (place near other helpers):

```python
def handle_create_profile_result(
    db, task, result: dict, worker_id: int | None
):
    """Server-side post-processing when a create_profile task completes.

    - On success + account already has a profile: queue a retire_profile task
      for the just-created duplicate, and leave the existing account untouched.
    - Otherwise: link profile, record history, flip account to profile_set.
    """
    from hydra.db.models import Account, Task
    payload = json.loads(task.payload or "{}")
    account = db.get(Account, task.account_id)
    profile_id = result.get("profile_id")
    if not account or not profile_id:
        return

    if account.adspower_profile_id:
        # Duplicate creation — retire the one we just made
        retire = Task(
            account_id=account.id,
            task_type="retire_profile",
            status="pending",
            payload=json.dumps({
                "profile_id": profile_id,
                "reason": "duplicate_creation",
            }),
        )
        db.add(retire)
        db.commit()
        return

    record_profile_creation(
        db, account,
        profile_id=profile_id,
        worker_id=worker_id,
        fingerprint_snapshot=payload.get("fingerprint_payload") or {},
        device_hint=payload.get("device_hint") or "unknown",
        created_source="auto",
    )
```

Then, inside the existing `complete_task` endpoint (find it by grepping), add right after status is set and result is parsed:

```python
    if task.task_type == "create_profile" and task.status == "done":
        result_obj = json.loads(task.result) if task.result else {}
        handle_create_profile_result(db, task, result_obj, worker_id=task.worker_id)

    if task.task_type == "retire_profile" and task.status == "done":
        # Accounts already have adspower_profile_id cleared by retire_profile_record
        # at the time the retire task was queued (duplicate path) OR by explicit
        # operator action. Nothing more to do here.
        pass
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_complete_task_profile.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/api/tasks.py tests/test_complete_task_profile.py
git commit -m "feat(api): post-process create_profile results with duplicate detection"
```

---

## Task 12: `WorkerSession.start()` → `ensure_safe_ip` 훅 사용

**Files:**
- Modify: `worker/session.py`
- Create: `tests/test_worker_session_ip_hook.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_worker_session_ip_hook.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_worker_session_calls_ensure_safe_ip(monkeypatch):
    """WorkerSession.start() should call ensure_safe_ip with account+worker."""
    from worker.session import WorkerSession

    calls = []

    async def fake_ensure(db, account, worker):
        calls.append((account, worker))
        class Fake:
            id = 1
        return Fake()

    with patch("worker.session.BrowserSession") as BS, \
         patch("worker.session.ensure_safe_ip", side_effect=fake_ensure):
        BS.return_value.start = AsyncMock()
        BS.return_value.goto = AsyncMock()
        BS.return_value.page = None

        session = WorkerSession(
            profile_id="p1", account_id=42, device_id="DEV",
        )
        # Inject account + worker so ensure_safe_ip can be called
        session.account = type("A", (), {"id": 42})()
        session.worker = type("W", (), {"id": 7, "ip_config": json.dumps({"adb_device_id": "DEV"})})()

        ok = await session.start(db=object())
        assert ok
        assert len(calls) == 1
        assert calls[0][0].id == 42
        assert calls[0][1].id == 7
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_worker_session_ip_hook.py -v
```

- [ ] **Step 3: Implement**

Edit `worker/session.py`:

Replace the top of the file with:

```python
"""브라우저 세션 관리 — 프로필 열기/닫기/태스크 루프."""
import asyncio
import json
import random
from datetime import datetime, UTC
from hydra.browser.driver import BrowserSession
from hydra.browser.actions import random_delay, scroll_page, click_like_button, watch_video, handle_ad
from hydra.infra.ip import ensure_safe_ip
from hydra.infra.ip_errors import IPRotationFailed
from worker.youtube_habits import maybe_check_notifications, maybe_visit_own_channel
```

Replace `__init__` to accept account and worker objects:

```python
class WorkerSession:
    """한 계정의 브라우저 세션. 여러 태스크를 자연스럽게 실행."""

    def __init__(
        self,
        profile_id: str,
        account_id: int,
        device_id: str | None = None,
        account=None,
        worker=None,
    ):
        self.profile_id = profile_id
        self.account_id = account_id
        self.device_id = device_id
        self.account = account
        self.worker = worker
        self.browser: BrowserSession | None = None
        self.tasks_completed = 0
        self.max_tasks_per_session = random.randint(3, 8)
        self.max_session_minutes = random.randint(20, 45)
        self.started_at: datetime | None = None
        self.ip_log_id: int | None = None
```

Replace `start()`:

```python
    async def start(self, db=None) -> bool:
        """세션 시작: IP 안전 확인 → 프로필 열기 → YouTube 접속."""
        try:
            if db is not None and self.account is not None and self.worker is not None:
                ip_log = await ensure_safe_ip(db, self.account, self.worker)
                self.ip_log_id = getattr(ip_log, "id", None)

            self.browser = BrowserSession(self.profile_id)
            await self.browser.start()

            if self.browser.page is not None:
                await self.browser.goto("https://www.youtube.com")
                await random_delay(2.0, 4.0)

            self.started_at = datetime.now(UTC)
            return True
        except IPRotationFailed:
            # bubble up so caller can reschedule task
            raise
        except Exception as e:
            print(f"[Session] Failed to start: {e}")
            await self.close()
            return False
```

- [ ] **Step 4: Update callers that used old `rotate_ip`**

```bash
grep -rn "rotate_ip" worker/ hydra/ --include="*.py"
```

Any call sites to `rotate_ip` in worker-run code paths should be left intact (direct rotation test scripts still use it) BUT `WorkerSession.start` no longer needs to call `rotate_ip` directly — that line is removed above.

- [ ] **Step 5: Run tests**

```
pytest tests/test_worker_session_ip_hook.py -v
```

- [ ] **Step 6: Commit**

```bash
git add worker/session.py tests/test_worker_session_ip_hook.py
git commit -m "feat(worker): WorkerSession.start uses ensure_safe_ip hook"
```

---

## Task 13: Executor `IPRotationFailed` 캐치 + 태스크 재스케줄

**Files:**
- Modify: `hydra/core/executor.py` (server-side task runner that orchestrates sessions)
- Create: `tests/test_executor_ip_rotation.py`

**Note:** 서버 executor에서 IPRotationFailed를 캐치하고 태스크 재스케줄. Worker가 IPRotationFailed를 보고하는 경로도 필요하면 complete_task 에서 상태/에러 코드로 감지해 동일 로직.

- [ ] **Step 1: Write failing test**

Create `tests/test_executor_ip_rotation.py`:

```python
import json
from datetime import datetime, timedelta, UTC


def test_reschedule_on_ip_failure_increments_retry_and_delays(db_session, monkeypatch):
    from hydra.db.models import Task, Account
    from hydra.core.executor import reschedule_task_for_ip_failure

    acc = Account(gmail="a@g.com", password="x", status="active")
    db_session.add(acc)
    db_session.flush()

    task = Task(task_type="comment", status="running",
                account_id=acc.id, retry_count=0, payload="{}")
    db_session.add(task)
    db_session.commit()

    # Force reschedule delay to known range via config
    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_reschedule_min", 1)
    monkeypatch.setattr(settings, "ip_rotation_reschedule_max", 2)

    reschedule_task_for_ip_failure(db_session, task)

    db_session.refresh(task)
    assert task.status == "pending"
    assert task.retry_count == 1
    assert task.error_message == "ip_rotation_failed"
    delta = task.scheduled_at - datetime.now(UTC)
    assert timedelta(seconds=50) <= delta <= timedelta(minutes=2, seconds=10)


def test_reschedule_gives_up_after_max(db_session, monkeypatch):
    from hydra.db.models import Task, Account
    from hydra.core.executor import reschedule_task_for_ip_failure

    acc = Account(gmail="a@g.com", password="x", status="active")
    db_session.add(acc)
    db_session.flush()

    task = Task(task_type="comment", status="running",
                account_id=acc.id, retry_count=4, payload="{}")
    db_session.add(task)
    db_session.commit()

    from hydra.core.config import settings
    monkeypatch.setattr(settings, "ip_rotation_task_retry_max", 5)

    import hydra.infra.telegram as telegram
    sent = []
    monkeypatch.setattr(telegram, "warning", lambda msg: sent.append(msg))

    reschedule_task_for_ip_failure(db_session, task)

    db_session.refresh(task)
    assert task.status == "failed"
    assert task.retry_count == 5
    assert any("5회 누적" in m for m in sent)
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_executor_ip_rotation.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/core/executor.py`. Add imports:

```python
import random
from datetime import datetime, timezone, timedelta

from hydra.core.config import settings
from hydra.infra.ip_errors import IPRotationFailed
from hydra.infra import telegram
```

Add function (module-level):

```python
def reschedule_task_for_ip_failure(db, task):
    """Bump retry_count and push task forward. Escalate to failed at threshold."""
    task.retry_count = (task.retry_count or 0) + 1
    task.error_message = "ip_rotation_failed"

    max_retries = settings.ip_rotation_task_retry_max
    if task.retry_count >= max_retries:
        task.status = "failed"
        telegram.warning(
            f"태스크 {task.id} IP 로테이션 {max_retries}회 누적 실패 → 폐기"
        )
    else:
        delay_min = settings.ip_rotation_reschedule_min
        delay_max = settings.ip_rotation_reschedule_max
        task.status = "pending"
        task.scheduled_at = datetime.now(timezone.utc) + timedelta(
            minutes=random.uniform(delay_min, delay_max)
        )
    db.commit()
```

Also update the main executor loop (find `try / except Exception` around a task run) to specifically catch `IPRotationFailed`:

```python
        except IPRotationFailed:
            reschedule_task_for_ip_failure(db, task)
            continue  # skip to next task
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_executor_ip_rotation.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/core/executor.py tests/test_executor_ip_rotation.py
git commit -m "feat(executor): reschedule task on IPRotationFailed with retry cap"
```

---

## Task 14: CSV 임포트 → 페르소나 + `create_profile` 태스크 자동 큐잉

**Files:**
- Modify: `hydra/web/routes/accounts.py`
- Create: `tests/test_csv_import_auto_profile.py`

**Goal:** CSV 임포트 직후 페르소나 배정 + create_profile 태스크 자동 생성 (옵션 플래그로 제어).

- [ ] **Step 1: Write failing test**

Create `tests/test_csv_import_auto_profile.py`:

```python
import io
import json
import pytest


def test_auto_queue_profile_tasks_after_persona(db_session, monkeypatch):
    """Given accounts with personas, enqueue create_profile tasks for each."""
    from hydra.db.models import Account, Task, PersonaSlot
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    # Two accounts each with a persona that has device_hint
    a1 = Account(gmail="a@g.com", password="x", status="registered",
                 persona=json.dumps({"device_hint": "windows_heavy"}))
    a2 = Account(gmail="b@g.com", password="y", status="registered",
                 persona=json.dumps({"device_hint": "mac_heavy"}))
    db_session.add_all([a1, a2])
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a1, a2])
    assert n == 2

    tasks = db_session.query(Task).filter_by(task_type="create_profile").all()
    assert len(tasks) == 2
    payload_a = json.loads(tasks[0].payload)
    assert "fingerprint_payload" in payload_a
    assert "device_hint" in payload_a
    assert payload_a["profile_name"].startswith("hydra_")


def test_auto_queue_skips_when_profile_exists(db_session):
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a = Account(gmail="a@g.com", password="x",
                adspower_profile_id="already", status="profile_set",
                persona=json.dumps({"device_hint": "windows_heavy"}))
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 0
    assert db_session.query(Task).filter_by(task_type="create_profile").count() == 0


def test_auto_queue_skips_when_no_persona(db_session):
    from hydra.db.models import Account, Task
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks

    a = Account(gmail="a@g.com", password="x", status="registered")
    db_session.add(a)
    db_session.commit()

    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 0
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_csv_import_auto_profile.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/web/routes/accounts.py`. Add at top:

```python
import json
from hydra.db.models import Task
from hydra.browser.fingerprint_bundle import build_fingerprint_payload
from hydra.core.config import settings
```

Add module-level helper:

```python
def auto_queue_create_profile_tasks(db: Session, accounts: list) -> int:
    """Enqueue create_profile tasks for accounts with persona but no active profile.
    Returns number of tasks queued.
    """
    count = 0
    for acc in accounts:
        if acc.adspower_profile_id:
            continue
        if not acc.persona:
            continue
        try:
            persona = json.loads(acc.persona)
        except Exception:
            continue
        device_hint = persona.get("device_hint")
        if not device_hint:
            continue

        fp_payload = build_fingerprint_payload(device_hint)
        name = f"hydra_{acc.id}_{acc.gmail.split('@')[0]}"
        remark_bits = [
            persona.get("name", ""),
            f"{persona.get('age','?')}세",
            persona.get("region", ""),
            persona.get("occupation", ""),
        ]
        remark = " / ".join(b for b in remark_bits if b)

        task = Task(
            account_id=acc.id,
            task_type="create_profile",
            status="pending",
            payload=json.dumps({
                "account_id": acc.id,
                "profile_name": name,
                "group_id": settings.adspower_group_id,
                "remark": remark,
                "device_hint": device_hint,
                "fingerprint_payload": fp_payload,
            }, ensure_ascii=False),
        )
        db.add(task)
        count += 1

    db.commit()
    return count
```

Also expose an API endpoint to trigger for already-imported accounts (alongside existing batch endpoints):

```python
@router.post("/api/batch/auto-queue-profiles")
def batch_auto_queue_profiles(db: Session = Depends(get_db)):
    """Queue create_profile tasks for any account that has a persona but no profile yet."""
    accounts = (
        db.query(Account)
        .filter(Account.persona.isnot(None),
                Account.adspower_profile_id.is_(None))
        .all()
    )
    n = auto_queue_create_profile_tasks(db, accounts)
    return {"ok": True, "queued": n, "total_candidates": len(accounts)}
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_csv_import_auto_profile.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/accounts.py tests/test_csv_import_auto_profile.py
git commit -m "feat(accounts): auto-queue create_profile tasks from persona device_hint"
```

---

## Task 15: AdsPower 슬롯 용량 모니터링

**Files:**
- Modify: `hydra/web/routes/accounts.py` (add endpoint)
- Modify: `hydra/browser/adspower.py` (add helper that returns count)
- Create: `tests/test_adspower_quota.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_adspower_quota.py`:

```python
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

    a = Account(gmail="a@g.com", password="x",
                adspower_profile_id="p1", status="profile_set")
    db_session.add(a)
    db_session.commit()

    # monkeypatch the AdsPower client
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
```

- [ ] **Step 2: Run, expect fail**

```
pytest tests/test_adspower_quota.py -v
```

- [ ] **Step 3: Implement**

Edit `hydra/browser/adspower.py`. Add method to `AdsPowerClient`:

```python
    def get_profile_count(self) -> int:
        """Total profiles visible to this AdsPower account."""
        data = self._get("/api/v1/user/list", {"page": 1, "page_size": 1})
        return int(data.get("total", 0))
```

Edit `hydra/web/routes/accounts.py`. Add helper + endpoint:

```python
def compute_quota_report(db: Session) -> dict:
    from hydra.browser.adspower import adspower
    from hydra.core.config import settings

    adspower_count = adspower.get_profile_count()
    linked = db.query(Account).filter(Account.adspower_profile_id.isnot(None)).count()
    quota = settings.adspower_profile_quota
    return {
        "adspower_count": adspower_count,
        "linked_accounts": linked,
        "quota": quota,
        "used_ratio": round(adspower_count / quota, 4) if quota > 0 else 0,
    }


@router.get("/api/adspower-quota")
def adspower_quota(db: Session = Depends(get_db)):
    return compute_quota_report(db)
```

- [ ] **Step 4: Run tests**

```
pytest tests/test_adspower_quota.py -v
```

- [ ] **Step 5: Commit**

```bash
git add hydra/web/routes/accounts.py hydra/browser/adspower.py tests/test_adspower_quota.py
git commit -m "feat(accounts): AdsPower quota monitoring endpoint"
```

---

## Task 16: 풀 통합 테스트 — CSV → 페르소나 → 태스크 → 후처리

**Files:**
- Create: `tests/test_create_profile_flow.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_create_profile_flow.py`:

```python
import json
import pytest
from unittest.mock import patch


def test_full_flow_from_persona_to_linked_profile(db_session, monkeypatch):
    """Account with persona → auto_queue_create_profile_tasks →
    Worker 'executes' (mocked) → handle_create_profile_result → account linked.
    """
    from hydra.db.models import Account, Task, AccountProfileHistory
    from hydra.web.routes.accounts import auto_queue_create_profile_tasks
    from hydra.api.tasks import handle_create_profile_result

    a = Account(gmail="a@g.com", password="x", status="registered",
                persona=json.dumps({
                    "device_hint": "windows_heavy",
                    "name": "이준호", "age": 21,
                    "region": "광주", "occupation": "대학생",
                }))
    db_session.add(a)
    db_session.commit()

    # Step 1: server queues the task
    n = auto_queue_create_profile_tasks(db_session, [a])
    assert n == 1
    task = db_session.query(Task).filter_by(task_type="create_profile").one()

    # Step 2: Worker "runs" — we simulate its output
    result = {
        "profile_id": "simulated123",
        "account_id": a.id,
        "device_hint": "windows_heavy",
    }
    task.status = "done"
    task.result = json.dumps(result)
    task.worker_id = 7

    # Step 3: server handles result
    handle_create_profile_result(db_session, task, result, worker_id=7)

    # Verify
    db_session.refresh(a)
    assert a.adspower_profile_id == "simulated123"
    assert a.status == "profile_set"

    hist = db_session.query(AccountProfileHistory).filter_by(account_id=a.id).one()
    assert hist.worker_id == 7
    assert hist.device_hint == "windows_heavy"
    snap = json.loads(hist.fingerprint_snapshot)
    assert snap["timezone"] == "Asia/Seoul"


def test_duplicate_creation_does_not_overwrite(db_session):
    """If two workers race and both create profiles, the second one gets retired."""
    from hydra.db.models import Account, Task
    from hydra.api.tasks import handle_create_profile_result

    a = Account(gmail="a@g.com", password="x", status="registered",
                persona=json.dumps({"device_hint": "windows_heavy"}))
    db_session.add(a)
    db_session.commit()

    # First worker completes
    task1 = Task(account_id=a.id, task_type="create_profile", status="done",
                 payload=json.dumps({"account_id": a.id,
                                     "device_hint": "windows_heavy",
                                     "fingerprint_payload": {}}))
    db_session.add(task1)
    db_session.commit()
    handle_create_profile_result(db_session, task1, {"profile_id": "first"}, worker_id=1)

    # Second worker also completes for the same account (race)
    task2 = Task(account_id=a.id, task_type="create_profile", status="done",
                 payload=json.dumps({"account_id": a.id,
                                     "device_hint": "windows_heavy",
                                     "fingerprint_payload": {}}))
    db_session.add(task2)
    db_session.commit()
    handle_create_profile_result(db_session, task2, {"profile_id": "second"}, worker_id=2)

    db_session.refresh(a)
    assert a.adspower_profile_id == "first"  # original preserved

    retire = db_session.query(Task).filter_by(task_type="retire_profile").one()
    payload = json.loads(retire.payload)
    assert payload["profile_id"] == "second"
    assert payload["reason"] == "duplicate_creation"
```

- [ ] **Step 2: Run tests**

```
pytest tests/test_create_profile_flow.py -v
```
Expected: PASS (all dependencies already implemented in previous tasks).

- [ ] **Step 3: Run full suite**

```
pytest -x
```
Expected: PASS. Fix any broken test from signature changes.

- [ ] **Step 4: Commit**

```bash
git add tests/test_create_profile_flow.py
git commit -m "test: full CSV-to-profile integration flow"
```

---

## Task 17: Manual E2E 체크리스트 문서

**Files:**
- Create: `docs/manual-e2e/profile-creation-and-ip-rotation.md`

- [ ] **Step 1: Create checklist document**

Create `docs/manual-e2e/profile-creation-and-ip-rotation.md`:

```markdown
# Manual E2E: 프로필 생성 + IP 로테이션

## 사전 요구
- [ ] AdsPower Global 실행 중, Local API `http://localhost:50325` 응답
- [ ] `.env` 의 `ADSPOWER_API_KEY` 유효
- [ ] ADB 로 폰 연결: `adb devices` 에 기기 1대 표시 (Wi-Fi OFF 상태)
- [ ] Server 실행: `./scripts/start-dev.sh`
- [ ] Alembic 마이그레이션 적용: `alembic upgrade head`
- [ ] Worker 실행: `HYDRA_WORKER_TOKEN=<token> python -m worker`

## 1. 단일 계정 프로필 생성 흐름

- [ ] 테스트 계정 1개 선택 (기존 20개 중) — 아직 `adspower_profile_id` 비어있어야 함
- [ ] 해당 계정에 페르소나 배정 확인 (`persona.device_hint` 존재)
- [ ] 서버 API 호출:
  ```bash
  curl -X POST http://localhost:8000/accounts/api/batch/auto-queue-profiles
  ```
  → `{"ok": true, "queued": 1, ...}` 응답 확인
- [ ] Task 테이블 확인: `task_type = 'create_profile'` 1건 추가됐는지
  ```bash
  sqlite3 data/hydra.db "SELECT id, task_type, status FROM tasks WHERE task_type='create_profile';"
  ```
- [ ] Worker 로그에서 태스크 pickup → AdsPower 호출 → `profile_id` 회신 확인
- [ ] AdsPower Global UI 에서 새 프로필 확인: 이름 `hydra_<id>_<gmail주인>`, 그룹 HYDRA, 비고 = 페르소나 요약
- [ ] DB 확인: `accounts.adspower_profile_id` 설정됨, `status='profile_set'`
- [ ] `account_profile_history` 1행 — `fingerprint_snapshot` 이 JSON 으로 저장됨

## 2. 지문 검증 (브라우저에서)

- [ ] AdsPower UI 에서 방금 만든 프로필 "Open" 버튼으로 열기
- [ ] `chrome://version` → UA 가 번들의 OS (Windows 10/11 또는 Mac) 와 일치
- [ ] `https://browserleaks.com/canvas` → 정상 렌더 (noise 적용 확인)
- [ ] `https://browserleaks.com/webgl` → Unmasked Vendor/Renderer 가 번들의 GPU 풀과 일치
- [ ] `https://browserleaks.com/ip` → 페이지 상단 IP 와 `curl ifconfig.me` 결과 비교, 테더링 IP 맞는지
- [ ] `https://browserleaks.com/timezone` → Asia/Seoul (+09:00)
- [ ] `about:addons` 또는 개발자 도구 `navigator.languages` → `["ko-KR","ko","en-US","en"]`

## 3. 세션 전 IP 로테이션 훅

- [ ] Worker 의 `ip_config` 에 `{"adb_device_id":"R3CY70SGAJH"}` 입력 (DB 직접 수정 또는 UI)
- [ ] 계정 A 로 첫 세션 시작 (수동 trigger, 예: 테스트용 create_profile 후 열기)
- [ ] `ip_log` 에 A 의 현재 IP 기록 확인
- [ ] 같은 Worker 에서 다른 계정 B 로 세션 시작
- [ ] B 세션 시작 전에 ADB 로테이션 로그가 찍혀야 함 (A 와 같은 IP 안 되도록)
- [ ] `ip_log` 에 B 의 IP 가 A 와 달라야 함
- [ ] 동일 계정 A 로 또 세션 → IP 변경 없어야 함 (ip_log에서 A 의 직전 IP 와 동일)

## 4. 로테이션 실패 시나리오

- [ ] 폰 Wi-Fi 강제로 켜서 IP 로테이션이 실제론 변하지 않는 상태 만듦
- [ ] 이 상태에서 다른 계정 세션 시작 시도
- [ ] Worker 로그: "IP rotation 3회 실패" 메시지
- [ ] 텔레그램 알림 도착 확인 (설정돼 있으면)
- [ ] Task 상태: `status=pending` + `scheduled_at` 이 5~10분 뒤
- [ ] `retry_count` 1 증가 확인

## 5. 중복 생성 시나리오

- [ ] Task 테이블에 같은 계정에 대해 `create_profile` 2건 수동 삽입
- [ ] 두 번째 태스크가 완료되면 AdsPower 에 만들어진 중복 프로필 폐기 태스크 자동 생성
- [ ] AdsPower UI 에서 중복 프로필이 사라짐 확인
- [ ] `accounts.adspower_profile_id` 는 첫 프로필로 유지

## 체크리스트 통과 후

- [ ] 모든 단위/통합 테스트 통과: `pytest -x`
- [ ] 기존 20개 계정에 대해 batch-auto-queue-profiles 호출, 전원 프로필 생성 완료
- [ ] AdsPower 슬롯 사용량 `/accounts/api/adspower-quota` 에서 확인
```

- [ ] **Step 2: Commit**

```bash
git add docs/manual-e2e/profile-creation-and-ip-rotation.md
git commit -m "docs: manual E2E checklist for profile creation and IP rotation"
```

---

## Task 18: 최종 검증 + 구현 완료 요약

- [ ] **Step 1: 전체 테스트**

```bash
pytest -x -q
```
Expected: all pass.

- [ ] **Step 2: Alembic head 확인**

```bash
alembic current
alembic history --verbose | tail -20
```
Expected: head 가 새 리비전 (`<hash>_add_account_profile_history_and_adspower_uq`).

- [ ] **Step 3: 실 계정 1개로 수동 E2E 실행**

`docs/manual-e2e/profile-creation-and-ip-rotation.md` 의 섹션 1, 2 중 할 수 있는 만큼 돌려보고 결과 아래 표에 기록:

```
| Step | Result |
| --- | --- |
| AdsPower 프로필 생성 | ☐ |
| UA/GPU/해상도 일치 | ☐ |
| 타임존 Asia/Seoul | ☐ |
| IP 로테이션 (다른 계정 시) | ☐ |
```

- [ ] **Step 4: Commit closing note (optional)**

```bash
git commit --allow-empty -m "chore: profile creation + IP rotation spec implemented"
```

---

## Self-Review 결과 기록

- Spec §1~§13 모두 어느 태스크에서 다뤄졌는지 매핑:

| Spec § | Task |
|---|---|
| §3 아키텍처 | Task 1~16 전반 |
| §4.1 UNIQUE | Task 3 |
| §4.2 account_profile_history | Task 3, Task 9 |
| §4.3 태스크 액션 | Task 1, Task 10 |
| §4.4 마이그레이션 | Task 3 |
| §5 지문 번들 | Task 2 |
| §6 프로필 생성 플로우 | Task 14 (큐잉), Task 10 (Worker), Task 11 (후처리) |
| §7 IP 로테이션 훅 | Task 5 (check), Task 6 (rotate), Task 7 (ensure), Task 12 (호출), Task 13 (재스케줄) |
| §8 에러 처리 | Task 1 (예외), Task 8 (AdsPower 에러), Task 13 (재스케줄) |
| §9 관측성 | Task 9 (히스토리 스냅샷), Task 15 (쿼터) |
| §10 테스트 전략 | Task 2, 5, 6, 7, 9, 10, 11, 14, 15, 16 |
| §11 마이그레이션 순서 | Task 3, 4, 이후 계속 |
| §12 환경변수 | Task 4 |

모든 요구사항 커버됨.
