# 프로필 생성 + 세션 전 IP 로테이션 설계

> 작성일: 2026-04-18
> 대상: HYDRA v2 — Phase C 준비 단계
> 후속: UI 관리 (생성 버튼 / 매핑 / 최초 로그인 도우미) 별도 스펙으로 분리

---

## 1. 개요

### 배경

- 계정 20개 DB 등재됨. 모든 계정 `adspower_profile_id`가 비어 있음.
- AdsPower에 수동 생성 프로필 1개(`k1bim9ga`)만 존재.
- 현재 `create_profile` 코드는 언어만 설정하고 나머지 전부 AdsPower 자동 생성 기본값 → 20개 프로필이 동일 패턴으로 찍혀 나올 위험 (클러스터 탐지).
- `accounts.adspower_profile_id`에 UNIQUE 제약 없음 → 중복 매핑 가능한 구멍.
- IP 로테이션 로직(`rotate_ip`)은 `svc data` 토글만 하고 "30분 내 다른 계정 충돌" 검증을 하지 않음 → 1 IP = 1 계정 원칙 강제력 부족.

### 목적

- **지문 레이어**: 페르소나(`device_hint`)에 기반한 "찐 사람 번들"로 AdsPower 프로필을 생성해 OS/UA/해상도/GPU/폰트/타임존 등이 현실적으로 일관되게 묶이도록 한다.
- **1:1 무결성**: 한 계정 ↔ 한 프로필을 DB 제약 + 코드 + 히스토리로 전방위 강제.
- **IP 안전성**: 브라우저 세션 시작 직전에 "같은 IP를 30분 내 다른 계정이 썼는지" 검증하고 필요 시 로테이트, 실패 시 태스크 재스케줄.

### 성공 기준

- 신규 프로필 20개 생성 후 `browserleaks.com` 등에서 OS/GPU/해상도/UA/타임존이 번들 정의와 일치.
- 같은 Worker에서 서로 다른 계정 2개 연속 실행 시 IP가 자동 교체되고, 같은 계정 연속 실행 시는 유지.
- `adspower_profile_id` UNIQUE 위반 시도 시 DB 레벨에서 즉시 실패.
- 프로필 폐기 → 재생성 시 `account_profile_history`에 2행 (이전 retired_at 설정, 신규 활성)이 트랜잭션 1회로 기록.

---

## 2. 범위

### In scope

- `build_fingerprint_payload(device_hint)` 순수 함수 (device_hint → AdsPower `fingerprint_config` dict)
- `accounts.adspower_profile_id` UNIQUE 제약 (Alembic 마이그레이션)
- `account_profile_history` 신규 테이블
- 태스크 액션 2종 추가: `create_profile`, `retire_profile`
- CSV 임포트 → 페르소나 자동 배정 → `create_profile` 태스크 자동 큐잉
- Worker 측 `handle_create_profile` 핸들러 (기존 AdsPower 클라이언트 활용)
- Server 측 `complete_task` 후처리 (account 갱신 + 히스토리 기록 + 중복 감지)
- `ensure_safe_ip(account, worker)` 훅을 `open_browser` 진입 직전에 주입
- `rotate_and_verify()` 즉시 재시도 3회 + 30분 cross-account 규칙 검증
- `IPRotationFailed` → 태스크 5~10분 랜덤 지연 재스케줄
- AdsPower 슬롯 사용량 모니터링 (경고 알림, 100% 도달 시 자동 큐잉 차단)
- 단위/통합/E2E 테스트 골격

### Out of scope (후속 스펙)

- 프로필 관리 UI (개별 생성/일괄/매핑/폐기 버튼, AdsPower 기존 프로필 매핑)
- 최초 로그인 도우미 UI (브라우저 열기 + "로그인 완료" 체크)
- Gmail 이름 ↔ 한국 페르소나 불일치 교정 (별도 이슈)
- 지문 드리프트 시뮬 (장기 운영 데이터 보고 결정)
- 멀티 리전 (미국/일본 페르소나) 지원
- AdsPower 클라우드 동기화 지연 감지 및 명시적 대기

---

## 3. 아키텍처

### 분산 구성

```
┌──────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   Server     │       │  Worker PC #1   │       │  Worker PC #2   │
│  FastAPI+DB  │──WS──▶│  AdsPower 로컬  │       │  AdsPower 로컬  │
│              │       │  + USB/Wi-Fi 폰 │       │  + USB/Wi-Fi 폰 │
└──────────────┘       └─────────────────┘       └─────────────────┘
     ↑                         ↕ 클라우드 sync          ↕
     │                     ┌─────────────────────────┐
     │ profile_id만 저장   │  AdsPower Cloud         │
     │                     │  (프로필 쿠키/지문 동기) │
     │                     └─────────────────────────┘
```

### 핵심 원칙

- **프로필 이동성**: AdsPower 클라우드 sync로 여러 Worker에서 같은 프로필 접근 가능. 단 **동시 사용 금지** (`ProfileLock`).
- **Worker pin 없음**: 태스크는 온라인 Worker 아무나 pull. 계정이 특정 Worker에 묶이지 않음.
- **진실의 원천은 Server**: 지문 번들 계산/페르소나 할당은 Server, Worker는 단순 실행자.
- **1 계정 = 1 프로필**: 생애주기 내내 1:1 불변. 폐기 시 덮어쓰지 않고 히스토리에 행 2개.

### 컴포넌트 책임

| 파일 | 책임 |
|---|---|
| `hydra/browser/fingerprint_bundle.py` (신규) | `build_fingerprint_payload(device_hint)` 순수 함수 + GPU/폰트/해상도 풀 상수 |
| `hydra/browser/adspower.py` (확장) | AdsPower 로컬 API 호출 (변경 최소) |
| `hydra/accounts/manager.py` (수정) | `create_adspower_profile` 시그니처 변경, 히스토리 기록 추가 |
| `hydra/infra/ip.py` (확장) | `ensure_safe_ip`, `rotate_and_verify` 추가; `check_ip_available` 규칙 수정 |
| `hydra/browser/session.py` (수정) | `open_browser` 진입 시 `ensure_safe_ip` 훅 호출 |
| `hydra/core/executor.py` (수정) | `IPRotationFailed` 캐치 + 재스케줄 |
| `worker/executor.py` (확장) | `handle_create_profile`, `handle_retire_profile` 핸들러 |
| `hydra/api/tasks.py` (수정) | `complete_task`에 `create_profile` 후처리 분기 |
| `hydra/db/models.py` (수정) | `AccountProfileHistory` 모델 + UNIQUE 제약 |

---

## 4. 데이터 모델

### 4.1 `accounts` 테이블 변경

```python
# 기존 컬럼 adspower_profile_id 에 UNIQUE 추가
# NULL 다중 허용 (SQLite partial index)
op.create_index(
    "uq_accounts_adspower_profile_id",
    "accounts",
    ["adspower_profile_id"],
    unique=True,
    sqlite_where=text("adspower_profile_id IS NOT NULL"),
)
```

### 4.2 `account_profile_history` 신규 테이블

```python
class AccountProfileHistory(Base):
    __tablename__ = "account_profile_history"

    id                   = Column(Integer, primary_key=True, autoincrement=True)
    account_id           = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id            = Column(Integer, ForeignKey("workers.id"), nullable=True)
    adspower_profile_id  = Column(String, nullable=False)
    fingerprint_snapshot = Column(Text, nullable=True)   # JSON, 생성 시점 번들 전체
    created_source       = Column(String, nullable=False, default="auto")  # "auto" | "manual_mapped"
    device_hint          = Column(String, nullable=True)  # 생성 당시 값
    created_at           = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    retired_at           = Column(DateTime, nullable=True)
    retire_reason        = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_profhist_account", "account_id"),
        Index("idx_profhist_active", "account_id", "retired_at"),
    )
```

**불변 규칙:**
- `accounts.adspower_profile_id IS NOT NULL` ⇔ `history` 내 해당 account 행 중 `retired_at IS NULL`인 1행 존재, `adspower_profile_id` 일치.
- 새 프로필 생성/교체는 반드시 `account` 갱신 + `history` 삽입을 **같은 트랜잭션**.

### 4.3 태스크 액션 확장

`Task.action` 문자열 enum에 추가:
- `create_profile`: Worker가 로컬 AdsPower에 프로필 생성 요청
- `retire_profile`: Worker가 로컬 AdsPower에서 프로필 삭제 요청

`Task.payload`(JSON) 스키마 — `create_profile` 용:
```json
{
  "account_id": 1,
  "profile_name": "hydra_1_phamminhha29031999",
  "group_id": "9265234",
  "remark": "이준호 / 21세 / 광주 / 대학생",
  "device_hint": "windows_heavy",
  "fingerprint_payload": { /* AdsPower fingerprintConfig, 섹션 5.2/5.6 참조 */ }
}
```

### 4.4 기존 데이터 마이그레이션

- UNIQUE 추가 시 현재 데이터 중복 있는지 확인 (현 20개 중 `adspower_profile_id` 있는 계정 0건 → 무중복)
- 기존 `adspower_profile_id` 값이 있는 계정이 있으면 `history`에 `created_source='manual_mapped'`, `device_hint=NULL`, `fingerprint_snapshot=NULL`로 1행씩 삽입
- 마이그레이션 스크립트 `alembic/versions/<rev>_profile_history.py`에 상기 로직 포함

---

## 5. 지문 번들

### 5.1 번들 매트릭스

| 필드 | windows_heavy | windows_10_heavy | mac_heavy |
|---|---|---|---|
| OS UA (`random_ua.ua_system_version`) | `["Windows 10","Windows 11"]` 50/50 | `["Windows 10"]` | `["Mac OS X 14","Mac OS X 15"]` 40/60 |
| `screen_resolution` | 1920×1080 (55%) / 2560×1440 (25%) / 1366×768 (20%) | 1920×1080 (70%) / 1366×768 (30%) | 1440×900 (25%) / 1680×1050 (20%) / 2560×1440 (25%) / 2880×1800 (30%) |
| `hardware_concurrency` | 4 (20%) / 6 (30%) / 8 (50%) | 2 (30%) / 4 (70%) | 8 (60%) / 16 (40%) |
| `device_memory` | 4 (30%) / 8 (70%) | 4 (50%) / 8 (50%) | 8 (100%) |
| `webgl_config` vendor/renderer | Windows GPU 풀에서 가중 랜덤 | Windows GPU 풀에서 가중 랜덤 | Apple GPU 풀에서 가중 랜덤 |
| `fonts` | Windows 한글 폰트셋 (고정 리스트) | 동일 | Mac 한글 폰트셋 (고정 리스트) |

**`mixed`**: `windows_heavy`와 `mac_heavy`를 50/50 롤 후 해당 번들로 위임.

### 5.2 공통 필드 (모든 번들)

```python
COMMON_FP = {
    "browser_kernel_config": {"version": "ua_auto", "type": "chrome"},
    "automatic_timezone": "0",
    "timezone": "Asia/Seoul",
    "language_switch": "0",
    "language": ["ko-KR", "ko", "en-US", "en"],
    "location_switch": "1",
    "webrtc": "disabled",
    "canvas": "1", "webgl_image": "1", "audio": "1", "client_rects": "1",
    "webgl": "2",
    "device_name_switch": "1",       # Worker PC 이름 mask
    "mac_address_config": {"model": "1"},  # Worker MAC match
    "media_devices": "2",
    "speech_switch": "1",
    "scan_port_type": "1",
}
```

### 5.3 GPU 풀

```python
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
```

### 5.4 폰트 리스트

```python
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
```

### 5.5 media_devices 랜덤 규칙

```python
# 데스크톱 기본 가정 (카메라 1, 마이크 1~2, 스피커 1~2)
MEDIA_DEVICES_RANGE = {
    "audioinput_num": (1, 2),     # 내장 + 외장 랜덤
    "videoinput_num": (1, 1),     # 노트북 내장만 가정
    "audiooutput_num": (1, 2),    # 내장 스피커 + 이어폰 랜덤
}
```

### 5.6 함수 시그니처

```python
# hydra/browser/fingerprint_bundle.py

def build_fingerprint_payload(device_hint: str) -> dict:
    """
    device_hint: "windows_heavy" | "mac_heavy" | "windows_10_heavy" | "mixed"
    Returns: AdsPower fingerprint_config dict (섹션 3.4 예시 형태).
    
    순수 함수. 매 호출마다 번들 내 확률 분포에 따라 구체 값 랜덤 선택.
    random.seed를 외부에서 통제하지 않음 (테스트 시 monkeypatch).
    """
```

---

## 6. 프로필 생성 플로우

### 6.1 CSV 임포트 → 태스크 큐잉 (Server)

```python
# hydra/web/routes/accounts.py /upload-csv 또는 batch_setup

for account in imported_accounts:
    # 페르소나 자동 배정
    slot = claim_slot(db, account.id)
    persona = generate_persona(slot)
    account.persona = json.dumps(persona, ensure_ascii=False)
    
    # 지문 번들 계산 (Server에서)
    fingerprint_payload = build_fingerprint_payload(slot.device_hint)
    
    # create_profile 태스크 큐잉
    task = Task(
        action="create_profile",
        account_id=account.id,
        payload=json.dumps({
            "account_id": account.id,
            "profile_name": f"hydra_{account.id}_{account.gmail.split('@')[0]}",
            "group_id": settings.adspower_group_id,  # 환경변수화
            "remark": f"{persona['name']} / {persona['age']}세 / {persona['region']} / {persona['occupation']}",
            "device_hint": slot.device_hint,
            "fingerprint_payload": fingerprint_payload,
        }, ensure_ascii=False),
        status="pending",
        scheduled_at=datetime.now(UTC),
    )
    db.add(task)

db.commit()
```

### 6.2 Worker 측 실행

```python
# worker/executor.py

async def handle_create_profile(task, server_client):
    payload = json.loads(task.payload)
    
    # AdsPower 슬롯 용량 선체크 (옵션)
    # list_profiles().total + 1 > quota → 즉시 실패
    
    try:
        result = await adspower_client.post("/api/v1/user/create", {
            "name": payload["profile_name"],
            "group_id": payload["group_id"],
            "remark": payload["remark"],
            "user_proxy_config": {"proxy_soft": "no_proxy"},
            "fingerprint_config": payload["fingerprint_payload"],
        })
        profile_id = result["data"]["id"]
    except AdsPowerQuotaExceeded:
        await server_client.complete_task(
            task.id, status="failed", error="adspower_quota_exceeded"
        )
        return
    except AdsPowerAPIError as e:
        # 재시도는 서버가 스케줄 (지수 백오프)
        await server_client.complete_task(
            task.id, status="failed", error=f"adspower_api: {e}"
        )
        return
    
    await server_client.complete_task(
        task.id,
        status="done",
        result={"profile_id": profile_id, "worker_id": self.worker.id},
    )
```

### 6.3 Server 측 후처리

```python
# hydra/api/tasks.py complete_task()

if task.action == "create_profile" and status == "done":
    account = db.get(Account, task.account_id)
    profile_id = result["profile_id"]
    worker_id = result["worker_id"]
    payload = json.loads(task.payload)
    
    # 중복 생성 감지
    if account.adspower_profile_id is not None:
        # 누가 그 사이에 프로필 만들었음 → 방금 만든 profile 폐기 태스크 큐잉
        retire_task = Task(
            action="retire_profile",
            account_id=account.id,
            payload=json.dumps({"profile_id": profile_id, "reason": "duplicate"}),
            status="pending",
        )
        db.add(retire_task)
        db.commit()
        return
    
    # 정상 — account + history 한 번의 commit 으로
    account.adspower_profile_id = profile_id
    account.status = AccountStatus.PROFILE_SET
    db.add(AccountProfileHistory(
        account_id=account.id,
        worker_id=worker_id,
        adspower_profile_id=profile_id,
        fingerprint_snapshot=json.dumps(payload["fingerprint_payload"]),
        created_source="auto",
        device_hint=payload["device_hint"],
    ))
    db.commit()  # UNIQUE 제약 위반 시 여기서 IntegrityError 전파
```

### 6.4 프로필 폐기 (retire) 흐름

```python
# hydra/accounts/manager.py

def retire_profile(db: Session, account: Account, reason: str):
    if not account.adspower_profile_id:
        return
    
    # history 의 활성 행 찾기
    active = (
        db.query(AccountProfileHistory)
        .filter_by(account_id=account.id, retired_at=None)
        .one()
    )
    
    # retire_profile 태스크 큐잉
    task = Task(
        action="retire_profile",
        account_id=account.id,
        payload=json.dumps({"profile_id": account.adspower_profile_id, "reason": reason}),
        status="pending",
    )
    db.add(task)
    
    # DB 상태는 Worker 완료 보고 시점에 업데이트 (accounts.adspower_profile_id = None,
    # history.retired_at 설정)
    db.commit()
```

---

## 7. 세션 전 IP 로테이션 훅

### 7.1 `open_browser` 수정

```python
# hydra/browser/session.py

@asynccontextmanager
async def open_browser(profile_id: str, account: Account, worker: Worker):
    acquire_profile_lock(profile_id, worker_id=worker.id)
    ip_log = None
    try:
        ip_log = await ensure_safe_ip(db, account, worker)  # ← NEW
        ws = adspower.start_browser(profile_id)
        # ... Playwright CDP 연결 ...
        yield session
    finally:
        adspower.stop_browser(profile_id)
        release_profile_lock(profile_id)
        if ip_log:
            end_ip_usage(db, ip_log.id)
```

### 7.2 `ensure_safe_ip`

```python
# hydra/infra/ip.py

async def ensure_safe_ip(db: Session, account: Account, worker: Worker) -> IpLog:
    """세션 전 IP 안전 보장.
    
    1. Worker.ip_config 에서 adb_device_id 파싱. 없으면 로테이션 스킵 + ip_log만 기록.
    2. 현재 폰 IP 조회.
    3. 30분 내 '다른 계정이 같은 IP' 썼는지 체크 (check_ip_available).
    4. 안전 → ip_log 신규 기록 후 반환.
    5. 충돌 → rotate_and_verify() 실행. 실패 시 IPRotationFailed 전파.
    """
    ip_config = json.loads(worker.ip_config or "{}")
    device_id = ip_config.get("adb_device_id")
    
    if not device_id:
        # 테스트/프록시 미사용 환경 — 로테이션 없이 현재 IP 기록만
        current_ip = await _get_worker_external_ip()  # Worker 자체 IP
        return log_ip_usage(db, account.id, current_ip, "none")
    
    current_ip = await _get_current_ip(device_id)
    
    if check_ip_available(db, current_ip, account.id, cooldown_minutes=30):
        return log_ip_usage(db, account.id, current_ip, device_id)
    
    new_ip = await rotate_and_verify(db, device_id, account.id)
    return log_ip_usage(db, account.id, new_ip, device_id)
```

### 7.3 `check_ip_available` 규칙 수정

```python
def check_ip_available(
    db: Session,
    ip_address: str,
    account_id: int,
    cooldown_minutes: int = 30,
) -> bool:
    """같은 IP를 30분 내 '다른 계정'이 썼는지 확인.
    같은 계정 재사용은 허용 (실사람도 재접속 시 같은 IP 자주 얻음)."""
    cutoff = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
    conflict = (
        db.query(IpLog)
        .filter(
            IpLog.ip_address == ip_address,
            IpLog.started_at >= cutoff,
            IpLog.account_id != account_id,  # ← 추가 조건
        )
        .first()
    )
    return conflict is None
```

### 7.4 `rotate_and_verify`

```python
class IPRotationFailed(RuntimeError):
    pass

async def rotate_and_verify(db: Session, device_id: str, account_id: int) -> str:
    """로테이트 + 30분 cross-account 룰 검증. 즉시 재시도 3회."""
    previous_ip = await _get_current_ip(device_id)
    
    for attempt in range(1, 4):
        log.info(f"IP rotation attempt {attempt}/3 (prev: {previous_ip})")
        
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
            log.warning(f"Attempt {attempt}: IP unchanged")
            continue
        
        if check_ip_available(db, new_ip, account_id, cooldown_minutes=30):
            log.info(f"IP rotated safely: {previous_ip} → {new_ip}")
            return new_ip
        
        log.warning(f"Attempt {attempt}: new IP {new_ip} still conflicts")
        previous_ip = new_ip
    
    telegram.warning(
        f"⚠️ IP 로테이션 3회 실패 — device={device_id}, account_id={account_id}"
    )
    raise IPRotationFailed(f"Failed to obtain safe IP (device={device_id})")
```

### 7.5 태스크 재스케줄

```python
# hydra/core/executor.py

except IPRotationFailed:
    task.retry_count = (task.retry_count or 0) + 1
    task.last_error = "ip_rotation_failed"
    task.scheduled_at = datetime.now(UTC) + timedelta(
        minutes=random.uniform(5, 10)
    )
    if task.retry_count >= 5:
        task.status = "failed"
        telegram.warning(
            f"태스크 {task.id} IP 로테이션 5회 누적 실패 → 폐기"
        )
    db.commit()
    return  # 현재 순회 종료, 다른 태스크 처리
```

---

## 8. 에러 처리 통합표

| 에러 | 발생 위치 | 처리 | 재시도 | 알림 |
|---|---|---|---|---|
| `IPRotationFailed` | `ensure_safe_ip` | 태스크 재스케줄 (5~10분 랜덤) | 최대 5회 누적 → `failed` | `rotate_and_verify` 내부 3회 모두 실패 시마다 텔레그램 1회 |
| `ADBDeviceNotFound` | `_adb_shell` | 태스크 `failed` | 없음 | 즉시 텔레그램 |
| `AdsPowerQuotaExceeded` | `create_profile` | 태스크 `failed`, 큐잉 차단 플래그 설정 | 없음 | 즉시 텔레그램 긴급 |
| `AdsPowerAPIError` | AdsPower HTTP | 지수 백오프 (30s → 2m → 10m) | 최대 3회 | 3회 실패 시 텔레그램 |
| `ProfileLockTimeout` | `acquire_profile_lock` | 5분 뒤 재시도 | 최대 10회 | 10회 실패 시 텔레그램 |
| Worker crash (running 고아) | heartbeat timeout 5분 | `running → pending` 복귀 | 1회 (idempotency) | 5개 이상 동시 고아 시 텔레그램 |
| `DuplicateProfileCreation` | `complete_task` | 후발 profile 폐기 태스크 큐잉 | 없음 | 로그만 |

---

## 9. 관측성

### 로깅

- 모든 IP 로테이션 시도: `prev_ip`, `new_ip`, `attempt`, `result`
- 프로필 생성: `account_id`, `device_hint`, `profile_id`, `worker_id`, `duration_ms`
- `fingerprint_snapshot` 은 `account_profile_history` 에 full payload로 저장 (분석용)

### 대시보드 지표 (추가 UI는 후속 스펙이나 수치 집계는 이 스펙에서 제공)

- AdsPower 슬롯 사용량 (`used / total`)
- Worker별 IP 로테이션 성공률 (최근 7일)
- device_hint별 프로필 생성 성공/실패 건수
- 활성 프로필 수 vs 계정 수 (mismatch 시 경고)

---

## 10. 테스트 전략

### 10.1 단위 테스트

**`tests/test_fingerprint_bundle.py`**
- 각 `device_hint` 호출 시 필수 필드 전부 포함
- 1000회 롤 → 확률 분포가 정의와 ±5% 이내
- `mixed` 는 내부적으로 `windows_heavy` / `mac_heavy` 50/50 위임
- OS ↔ GPU 불일치 금지 (Mac UA + NVIDIA GPU 절대 불가)
- OS ↔ 폰트 일치 (Mac UA 면 폰트에 Apple SD Gothic Neo 포함, Windows 면 Malgun Gothic)

**`tests/test_ip_rotation.py`**
- `check_ip_available`: 같은 계정 재사용 OK / 다른 계정 충돌 체크
- `ensure_safe_ip` 분기 3가지 (안전 / 충돌 + 로테이트 성공 / 충돌 + 로테이트 실패)
- `rotate_and_verify` 재시도 루프 (mock `_adb_shell`, `_get_current_ip`)

**`tests/test_account_profile_history.py`**
- 생성 시 history 1행
- 폐기 → 재생성 시 `retired_at` 세팅 + 새 행 (같은 트랜잭션)
- UNIQUE 위반 시나리오 (같은 profile_id 두 계정에 저장 시도 → `IntegrityError`)

### 10.2 통합 테스트

- SQLite 인메모리 + mock AdsPower HTTP (`httpx` MockTransport)
- CSV 임포트 → 페르소나 → 태스크 큐잉 → Worker mock 실행 → 후처리 → `account.status == profile_set` 확인
- 중복 생성 시나리오: 동시 두 Worker 에서 같은 account 처리 → 한쪽만 성공, 다른 쪽은 폐기 태스크

### 10.3 E2E (수동)

실제 AdsPower + ADB 연결 Mac에서:
1. 테스트 계정 1개 CSV 임포트 → 자동 페르소나 + 프로필 생성 관찰
2. AdsPower UI 에서 새 프로필 확인 (이름/remark 기대값)
3. 프로필 열기 → `chrome://version`, `https://browserleaks.com/canvas`, `/webgl`, `/ip`, `/timezone` 에서 번들 정의와 일치 확인
4. 같은 Worker 에서 서로 다른 계정 2개 연속 실행 → 두 번째에 IP 로테이트 발생 관찰
5. 같은 계정 연속 실행 → IP 유지 관찰

---

## 11. 마이그레이션 계획

### 순서

1. Alembic revision 추가
   - `adspower_profile_id` UNIQUE 부분 인덱스 생성
   - `pinned_worker_id` 추가하지 **않음** (최종 설계에서 제외)
   - `account_profile_history` 테이블 생성
   - 백필: 기존 `adspower_profile_id` 있는 행은 `history` 에 `manual_mapped` 로 기록 (현재 0건)
2. 코드 배포 순서
   - `fingerprint_bundle.py` 신규 (함수/상수만, 호출 없음)
   - `AccountProfileHistory` 모델 + DB 마이그레이션
   - `adspower.py` 확장 (새 파라미터, 기본값 호환)
   - `ip.py` 에 `ensure_safe_ip`, `rotate_and_verify` 추가 (`rotate_ip` 는 유지; deprecation 예고 로그)
   - `session.py` `open_browser` 에 훅 주입 (기본 True, 환경변수로 끌 수 있음)
   - `worker/executor.py` 에 `handle_create_profile`/`handle_retire_profile` 추가
   - `tasks.py` `complete_task` 분기 추가
3. 기존 20개 계정은 CSV 재임포트 없이 "batch create profile" API 로 수동 트리거 (UI 는 후속 스펙에서)

### 롤백

- 마이그레이션 실패 시: `account_profile_history` drop + `adspower_profile_id` UNIQUE 제거
- 코드는 feature flag (`ENABLE_FINGERPRINT_BUNDLE=true`) 로 감싸 단계 전개

---

## 12. 환경변수 추가

| 이름 | 기본값 | 설명 |
|---|---|---|
| `ADSPOWER_GROUP_ID` | `"9265234"` | 프로필 생성 시 기본 그룹 ID (현재 "HYDRA" 그룹) |
| `ADSPOWER_PROFILE_QUOTA` | `100` | AdsPower 구독 슬롯 한도 (초과 시 큐잉 차단) |
| `ENABLE_FINGERPRINT_BUNDLE` | `true` | 번들 기반 지문 사용 여부 (false면 기존 언어만 설정) |
| `IP_ROTATION_COOLDOWN_MINUTES` | `30` | cross-account IP 쿨다운 |
| `IP_ROTATION_MAX_ATTEMPTS` | `3` | `rotate_and_verify` 재시도 횟수 |
| `IP_ROTATION_TASK_RETRY_MAX` | `5` | 태스크 누적 재시도 한도 |
| `IP_ROTATION_RESCHEDULE_MIN` | `5` | 재스케줄 지연 하한 (분) |
| `IP_ROTATION_RESCHEDULE_MAX` | `10` | 재스케줄 지연 상한 (분) |

---

## 13. 미루는 항목 (YAGNI)

- 지문 드리프트 시뮬 (n개월 후 폰트 추가 등) — 장기 운영 데이터 보고 결정
- WebGL canvas noise 수동 튜닝 — AdsPower 기본 noise가 충분
- IP 로테이션 쿨다운 길이 설정 UI — 상수 30분으로 시작, 나중에 설정화
- 멀티 리전 지원 — 현재 한국만
- AdsPower 클라우드 동기화 지연 명시적 감지 — 자동 sync 신뢰, 문제 생기면 추후
- 최초 로그인 도우미 UI — 후속 스펙
- 프로필 관리 UI (생성 버튼/매핑/폐기) — 후속 스펙
