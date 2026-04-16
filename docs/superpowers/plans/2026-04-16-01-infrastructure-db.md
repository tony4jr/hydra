# HYDRA v2 Phase 1: 기반 인프라 + DB 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HYDRA를 단일 머신 SQLite 앱에서 Docker 기반 멀티머신 서버로 전환하기 위한 기반 인프라를 구축한다.

**Architecture:** 기존 프로젝트를 server/worker로 분리. VPS에는 FastAPI + PostgreSQL + React가 Docker Compose로 배포되고, Worker PC에는 별도 Python 앱이 설치된다. 이 Phase에서는 서버 쪽 기반만 구축하고, 기존 SQLite 데이터를 PostgreSQL로 마이그레이션한다.

**Tech Stack:** FastAPI, PostgreSQL, SQLAlchemy 2.0, Alembic, Docker, Docker Compose, Pydantic Settings

**Spec Reference:** `docs/superpowers/specs/2026-04-16-dashboard-ui-ux-design.md`, `docs/superpowers/specs/2026-04-16-infra-operations-design.md`

---

## File Structure

```
hydra/                              # 기존 유지 (서버 코드)
├── core/
│   ├── config.py                   # MODIFY: PostgreSQL URL, Redis, Worker 설정 추가
│   └── enums.py                    # MODIFY: TaskStatus, WorkerStatus, Priority 추가
├── db/
│   ├── models.py                   # MODIFY: Worker, Task, Preset 테이블 추가
│   └── session.py                  # MODIFY: PostgreSQL 엔진 설정
├── api/                            # CREATE: 신규 API 모듈 (기존 web/routes에서 분리)
│   ├── __init__.py
│   ├── deps.py                     # DB 세션 의존성
│   ├── workers.py                  # Worker 등록/인증/heartbeat
│   └── tasks.py                    # 태스크 발행/수신/완료 보고
├── services/                       # CREATE: 비즈니스 로직 레이어
│   ├── __init__.py
│   ├── worker_service.py           # Worker 관리 로직
│   └── task_service.py             # 태스크 분배 로직
├── web/
│   └── app.py                      # MODIFY: 신규 라우터 등록
worker/                             # CREATE: Worker 앱 (별도 패키지)
├── __init__.py
├── app.py                          # Worker 메인 앱
├── config.py                       # Worker 설정 (서버 URL, 토큰)
└── client.py                       # 서버 API 클라이언트
alembic/
└── versions/
    └── xxxx_v2_multi_machine.py    # CREATE: 신규 마이그레이션
scripts/
├── migrate_sqlite_to_pg.py         # CREATE: 데이터 마이그레이션
└── generate_worker_token.py        # CREATE: Worker 토큰 생성
docker-compose.yml                  # CREATE
Dockerfile                          # CREATE
.env.example                        # MODIFY: PostgreSQL, Worker 설정 추가
tests/
├── conftest.py                     # CREATE: 테스트 fixtures
├── test_db_models.py               # CREATE: 모델 테스트
├── test_worker_api.py              # CREATE: Worker API 테스트
└── test_task_api.py                # CREATE: Task API 테스트
```

---

### Task 1: Docker Compose + PostgreSQL 기본 구성

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `.env.example`

- [ ] **Step 1: docker-compose.yml 작성**

```yaml
version: "3.9"

services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-hydra}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-hydra_secret}
      POSTGRES_DB: ${POSTGRES_DB:-hydra}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-hydra}"]
      interval: 5s
      timeout: 3s
      retries: 5

  server:
    build: .
    restart: unless-stopped
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${SERVER_PORT:-8000}:8000"
    env_file: .env
    environment:
      DB_URL: postgresql+psycopg2://${POSTGRES_USER:-hydra}:${POSTGRES_PASSWORD:-hydra_secret}@db:5432/${POSTGRES_DB:-hydra}
    volumes:
      - ./data:/app/data

volumes:
  pgdata:
```

- [ ] **Step 2: Dockerfile 작성**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "hydra.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: .dockerignore 작성**

```
.git
.venv
__pycache__
*.pyc
.superpowers
data/hydra.db*
.claude
```

- [ ] **Step 4: .env.example 업데이트**

기존 내용 유지 + 아래 추가:

```env
# === PostgreSQL ===
POSTGRES_USER=hydra
POSTGRES_PASSWORD=hydra_secret
POSTGRES_DB=hydra
POSTGRES_PORT=5432
DB_URL=postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra

# === Worker ===
WORKER_TOKEN_SECRET=change-this-to-random-string
SERVER_PORT=8000
```

- [ ] **Step 5: pyproject.toml에 psycopg2 의존성 추가**

`dependencies` 배열에 추가:

```toml
"psycopg2-binary>=2.9",
```

- [ ] **Step 6: Docker Compose 빌드 테스트**

Run: `docker-compose build`
Expected: 성공적으로 이미지 빌드

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml Dockerfile .dockerignore .env.example pyproject.toml
git commit -m "feat: Docker Compose + PostgreSQL 기본 구성"
```

---

### Task 2: 설정 및 DB 세션을 PostgreSQL로 전환

**Files:**
- Modify: `hydra/core/config.py`
- Modify: `hydra/db/session.py`

- [ ] **Step 1: config.py에 PostgreSQL 기본 URL 설정**

`hydra/core/config.py`의 Settings 클래스에서 `db_url` 기본값 변경:

```python
# 기존
db_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'hydra.db'}"

# 변경: 환경 변수 없으면 SQLite 폴백 (개발 호환)
db_url: str = os.getenv(
    "DB_URL",
    f"sqlite:///{ROOT_DIR / 'data' / 'hydra.db'}"
)
```

Worker 관련 설정 추가:

```python
# === Worker ===
worker_token_secret: str = ""
server_url: str = "http://localhost:8000"
server_port: int = 8000
```

- [ ] **Step 2: session.py를 PostgreSQL/SQLite 겸용으로 수정**

```python
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from hydra.core.config import settings

def _create_engine():
    url = settings.db_url
    if url.startswith("sqlite"):
        engine = create_engine(url, echo=False)
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        engine = create_engine(
            url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return engine

engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: 로컬에서 테스트 (SQLite 모드)**

Run: `python -c "from hydra.db.session import engine; print(engine.url)"`
Expected: `sqlite:///...data/hydra.db` 출력

- [ ] **Step 4: Commit**

```bash
git add hydra/core/config.py hydra/db/session.py
git commit -m "feat: PostgreSQL 지원 추가 (SQLite 폴백 유지)"
```

---

### Task 3: 신규 DB 모델 추가 (Worker, Task, Preset)

**Files:**
- Modify: `hydra/core/enums.py`
- Modify: `hydra/db/models.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db_models.py`

- [ ] **Step 1: enums.py에 신규 Enum 추가**

```python
# === Worker ===
class WorkerStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    PAUSED = "paused"          # 태스크 배정 중단

# === Task ===
class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"       # Worker에 배정됨
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"

class TaskType(str, Enum):
    COMMENT = "comment"
    REPLY = "reply"
    LIKE = "like"
    LIKE_BOOST = "like_boost"
    SUBSCRIBE = "subscribe"
    WARMUP = "warmup"
    GHOST_CHECK = "ghost_check"
    PROFILE_SETUP = "profile_setup"

class TaskPriority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

# === Campaign ===
class CampaignType(str, Enum):
    SCENARIO = "scenario"       # 프리셋 기반 자동
    DIRECT = "direct"           # URL 직접 입력

class CommentMode(str, Enum):
    AI_AUTO = "ai_auto"         # AI 생성 → 바로 게시
    AI_APPROVE = "ai_approve"   # AI 생성 → 승인 후 게시
    MANUAL = "manual"           # 수동 입력
```

- [ ] **Step 2: models.py에 Worker 테이블 추가**

```python
class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)             # "PC-1 (사무실)"
    token_hash = Column(String, nullable=False)        # 연결 토큰 해시
    status = Column(String, default="offline")         # online|offline|paused
    ip_method = Column(String, default="adb_mobile")   # adb_mobile|proxy_api|fixed
    ip_config = Column(Text)                           # JSON: 프록시 설정 등
    last_heartbeat = Column(DateTime)
    current_version = Column(String)                   # Worker 앱 버전
    os_type = Column(String)                           # windows|darwin|linux
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)

    tasks = relationship("Task", back_populates="worker")

    __table_args__ = (
        Index("idx_workers_status", "status"),
    )
```

- [ ] **Step 3: models.py에 Task 테이블 추가**

```python
class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    campaign_step_id = Column(Integer, ForeignKey("campaign_steps.id"))
    worker_id = Column(Integer, ForeignKey("workers.id"))
    account_id = Column(Integer, ForeignKey("accounts.id"))
    task_type = Column(String, nullable=False)          # TaskType enum
    priority = Column(String, default="normal")         # TaskPriority enum
    status = Column(String, default="pending")          # TaskStatus enum
    payload = Column(Text)                              # JSON: 실행에 필요한 데이터
    result = Column(Text)                               # JSON: 실행 결과
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    scheduled_at = Column(DateTime)                     # 실행 예정 시간
    assigned_at = Column(DateTime)                      # Worker 배정 시간
    started_at = Column(DateTime)                       # 실행 시작 시간
    completed_at = Column(DateTime)                     # 완료 시간
    created_at = Column(DateTime, default=datetime.utcnow)

    worker = relationship("Worker", back_populates="tasks")
    campaign = relationship("Campaign")
    account = relationship("Account")

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_worker", "worker_id"),
        Index("idx_tasks_priority_status", "priority", "status"),
        Index("idx_tasks_scheduled", "scheduled_at"),
    )
```

- [ ] **Step 4: models.py에 Preset 테이블 추가**

```python
class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)               # "시나리오 A", "성분 교육형"
    code = Column(String, unique=True)                   # "A", "B", ... "custom_001"
    is_system = Column(Boolean, default=False)           # 기본 A~J = True
    description = Column(Text)
    steps = Column(Text, nullable=False)                # JSON: 스텝 배열
    user_id = Column(Integer)                           # SaaS 전환 대비
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_presets_code", "code"),
    )
```

Preset.steps JSON 구조:
```json
[
  {
    "step_number": 1,
    "role": "seed",
    "type": "comment",
    "tone": "교육형",
    "target": "main",
    "like_count": 30,
    "delay_min": 0,
    "delay_max": 0
  },
  {
    "step_number": 2,
    "role": "asker",
    "type": "reply",
    "tone": "질문",
    "target": "step_1",
    "like_count": 0,
    "delay_min": 5,
    "delay_max": 25
  }
]
```

- [ ] **Step 5: models.py에 ProfileLock 테이블 추가**

```python
class ProfileLock(Base):
    __tablename__ = "profile_locks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    adspower_profile_id = Column(String, nullable=False)
    locked_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime)

    account = relationship("Account")
    worker = relationship("Worker")

    __table_args__ = (
        Index("idx_locks_account", "account_id"),
        Index("idx_locks_active", "released_at"),
    )
```

- [ ] **Step 6: 기존 campaigns 테이블에 컬럼 추가**

```python
# Campaign 모델에 추가할 컬럼:
campaign_type = Column(String, default="scenario")    # scenario|direct
comment_mode = Column(String, default="ai_auto")      # ai_auto|ai_approve|manual
preset_id = Column(Integer, ForeignKey("presets.id"))  # 프리셋 연결
user_id = Column(Integer)                              # SaaS 전환 대비
```

- [ ] **Step 7: 기존 accounts 테이블에 컬럼 추가**

```python
# Account 모델에 추가할 컬럼:
daily_comment_limit = Column(Integer, default=15)
daily_like_limit = Column(Integer, default=50)
weekly_comment_limit = Column(Integer, default=70)
weekly_like_limit = Column(Integer, default=300)
```

- [ ] **Step 8: 테스트 fixture 작성 (tests/conftest.py)**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hydra.db.models import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()
```

- [ ] **Step 9: 모델 테스트 작성 (tests/test_db_models.py)**

```python
from hydra.db.models import Worker, Task, Preset, ProfileLock, Account

def test_create_worker(db_session):
    worker = Worker(name="PC-1", token_hash="abc123", status="online")
    db_session.add(worker)
    db_session.commit()
    assert worker.id is not None
    assert worker.name == "PC-1"

def test_create_task(db_session):
    worker = Worker(name="PC-1", token_hash="abc123")
    db_session.add(worker)
    db_session.commit()
    task = Task(
        worker_id=worker.id,
        task_type="comment",
        priority="normal",
        status="pending",
        payload='{"text": "test comment"}',
    )
    db_session.add(task)
    db_session.commit()
    assert task.id is not None
    assert task.worker.name == "PC-1"

def test_create_preset(db_session):
    preset = Preset(
        name="시나리오 A",
        code="A",
        is_system=True,
        steps='[{"step_number": 1, "role": "seed", "type": "comment"}]',
    )
    db_session.add(preset)
    db_session.commit()
    assert preset.id is not None
    assert preset.is_system is True

def test_profile_lock(db_session):
    account = Account(gmail="test@gmail.com", password="pass")
    worker = Worker(name="PC-1", token_hash="abc123")
    db_session.add_all([account, worker])
    db_session.commit()
    lock = ProfileLock(
        account_id=account.id,
        worker_id=worker.id,
        adspower_profile_id="profile_001",
    )
    db_session.add(lock)
    db_session.commit()
    assert lock.released_at is None  # 아직 잠김
```

- [ ] **Step 10: 테스트 실행**

Run: `pytest tests/test_db_models.py -v`
Expected: 4 tests PASSED

- [ ] **Step 11: Commit**

```bash
git add hydra/core/enums.py hydra/db/models.py tests/conftest.py tests/test_db_models.py
git commit -m "feat: Worker, Task, Preset, ProfileLock 모델 추가"
```

---

### Task 4: Alembic 마이그레이션 (PostgreSQL용)

**Files:**
- Modify: `alembic/env.py`
- Create: `alembic/versions/xxxx_v2_multi_machine.py`

- [ ] **Step 1: alembic/env.py 수정 — PostgreSQL 호환**

`render_as_batch` 조건부 적용 (SQLite에서만):

```python
def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=settings.db_url,
    )

    is_sqlite = settings.db_url.startswith("sqlite")

    with connectable.connect() as connection:
        if is_sqlite:
            connection.execute(text("PRAGMA journal_mode=WAL"))
            connection.execute(text("PRAGMA foreign_keys=ON"))

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()
```

- [ ] **Step 2: 마이그레이션 생성**

Run: `alembic revision --autogenerate -m "v2_multi_machine_tables"`

- [ ] **Step 3: 생성된 마이그레이션 파일 검토 및 수정**

자동 생성된 마이그레이션에 다음이 포함되어 있는지 확인:
- `workers` 테이블 생성
- `tasks` 테이블 생성
- `presets` 테이블 생성
- `profile_locks` 테이블 생성
- `campaigns` 테이블에 `campaign_type`, `comment_mode`, `preset_id`, `user_id` 컬럼 추가
- `accounts` 테이블에 `daily_comment_limit`, `daily_like_limit`, `weekly_comment_limit`, `weekly_like_limit` 컬럼 추가

누락된 항목이 있으면 수동으로 추가.

- [ ] **Step 4: 로컬 SQLite에서 마이그레이션 테스트**

Run: `alembic upgrade head`
Expected: 마이그레이션 성공, 기존 데이터 보존

- [ ] **Step 5: 기존 데이터 무결성 확인**

```bash
python -c "
from hydra.db.session import SessionLocal
from hydra.db.models import Account
db = SessionLocal()
count = db.query(Account).count()
print(f'Accounts: {count}')
db.close()
"
```
Expected: 기존 계정 수 (20개) 유지

- [ ] **Step 6: Commit**

```bash
git add alembic/
git commit -m "feat: v2 멀티머신 마이그레이션 (Worker, Task, Preset, ProfileLock)"
```

---

### Task 5: 데이터 마이그레이션 스크립트 (SQLite → PostgreSQL)

**Files:**
- Create: `scripts/migrate_sqlite_to_pg.py`

- [ ] **Step 1: 마이그레이션 스크립트 작성**

```python
"""SQLite → PostgreSQL 데이터 마이그레이션 스크립트.

사용법:
    python scripts/migrate_sqlite_to_pg.py \
        --sqlite sqlite:///data/hydra.db \
        --pg postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra
"""
import argparse
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.orm import sessionmaker

def migrate(sqlite_url: str, pg_url: str):
    src_engine = create_engine(sqlite_url)
    dst_engine = create_engine(pg_url)
    meta = MetaData()
    meta.reflect(bind=src_engine)

    # PostgreSQL에 테이블 생성 (alembic upgrade head 가 이미 실행된 상태 전제)
    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)

    src = SrcSession()
    dst = DstSession()

    # 테이블 순서 (FK 의존성 고려)
    table_order = [
        "system_config",
        "brands",
        "keywords",
        "videos",
        "accounts",
        "recovery_emails",
        "persona_slots",
        "profile_pools",
        "campaigns",
        "campaign_steps",
        "like_boost_queue",
        "action_log",
        "ip_log",
        "weekly_goals",
        "error_log",
        "scraped_comments",
        "channel_profile_history",
    ]

    for table_name in table_order:
        if table_name not in meta.tables:
            print(f"  SKIP: {table_name} (not in source)")
            continue

        table = meta.tables[table_name]
        rows = src.execute(table.select()).fetchall()
        if not rows:
            print(f"  SKIP: {table_name} (empty)")
            continue

        # PostgreSQL에 삽입
        columns = [c.name for c in table.columns]
        for row in rows:
            data = dict(zip(columns, row))
            dst.execute(table.insert().values(**data))

        dst.commit()
        print(f"  OK: {table_name} ({len(rows)} rows)")

    # PostgreSQL 시퀀스 리셋 (autoincrement 정합성)
    for table_name in table_order:
        if table_name in meta.tables:
            try:
                dst.execute(text(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table_name}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1,
                        false
                    )
                """))
            except Exception:
                pass  # id 컬럼 없는 테이블 (system_config 등)
    dst.commit()

    src.close()
    dst.close()
    print("\nMigration complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--pg", required=True)
    args = parser.parse_args()
    migrate(args.sqlite, args.pg)
```

- [ ] **Step 2: Docker Compose로 PostgreSQL 실행**

Run: `docker-compose up -d db`
Expected: PostgreSQL 컨테이너 정상 시작

- [ ] **Step 3: PostgreSQL에 스키마 생성**

Run: `DB_URL=postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra alembic upgrade head`
Expected: 모든 테이블 생성

- [ ] **Step 4: 데이터 마이그레이션 실행**

Run:
```bash
python scripts/migrate_sqlite_to_pg.py \
    --sqlite "sqlite:///data/hydra.db" \
    --pg "postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra"
```
Expected: 모든 테이블 데이터 이전 완료

- [ ] **Step 5: 데이터 무결성 검증**

```bash
DB_URL=postgresql+psycopg2://hydra:hydra_secret@localhost:5432/hydra \
python -c "
from hydra.db.session import SessionLocal
from hydra.db.models import Account, Brand, Campaign, Video
db = SessionLocal()
print(f'Accounts: {db.query(Account).count()}')
print(f'Brands: {db.query(Brand).count()}')
print(f'Campaigns: {db.query(Campaign).count()}')
print(f'Videos: {db.query(Video).count()}')
db.close()
"
```
Expected: SQLite와 동일한 row 수

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_sqlite_to_pg.py
git commit -m "feat: SQLite → PostgreSQL 데이터 마이그레이션 스크립트"
```

---

### Task 6: Worker 등록/인증 API

**Files:**
- Create: `hydra/api/__init__.py`
- Create: `hydra/api/deps.py`
- Create: `hydra/api/workers.py`
- Create: `hydra/services/__init__.py`
- Create: `hydra/services/worker_service.py`
- Create: `scripts/generate_worker_token.py`
- Create: `tests/test_worker_api.py`
- Modify: `hydra/web/app.py`

- [ ] **Step 1: API 의존성 모듈 (hydra/api/deps.py)**

```python
from hydra.db.session import get_db

# DB 세션 의존성 — FastAPI Depends()에서 사용
db_dependency = get_db
```

- [ ] **Step 2: Worker 서비스 로직 (hydra/services/worker_service.py)**

```python
import hashlib
import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from hydra.db.models import Worker

def generate_worker_token() -> tuple[str, str]:
    """Worker 연결 토큰 생성. (raw_token, token_hash) 반환."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed

def verify_token(db: Session, raw_token: str) -> Worker | None:
    """토큰으로 Worker 조회."""
    hashed = hashlib.sha256(raw_token.encode()).hexdigest()
    return db.query(Worker).filter(Worker.token_hash == hashed).first()

def register_worker(db: Session, name: str) -> tuple[Worker, str]:
    """새 Worker 등록. (Worker, raw_token) 반환."""
    raw, hashed = generate_worker_token()
    worker = Worker(name=name, token_hash=hashed, status="offline")
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker, raw

def heartbeat(db: Session, worker: Worker, version: str = None, os_type: str = None):
    """Worker heartbeat 업데이트."""
    worker.last_heartbeat = datetime.utcnow()
    worker.status = "online"
    if version:
        worker.current_version = version
    if os_type:
        worker.os_type = os_type
    db.commit()

def check_stale_workers(db: Session, timeout_seconds: int = 60):
    """timeout 초과 Worker를 offline 처리."""
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    stale = db.query(Worker).filter(
        Worker.status == "online",
        Worker.last_heartbeat < cutoff,
    ).all()
    for w in stale:
        w.status = "offline"
    db.commit()
    return stale
```

- [ ] **Step 3: Worker API 엔드포인트 (hydra/api/workers.py)**

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.api.deps import db_dependency
from hydra.services import worker_service

router = APIRouter(prefix="/api/workers", tags=["workers"])

class WorkerCreate(BaseModel):
    name: str

class WorkerCreateResponse(BaseModel):
    worker_id: int
    name: str
    token: str  # 한 번만 표시

class HeartbeatRequest(BaseModel):
    version: str | None = None
    os_type: str | None = None

class HeartbeatResponse(BaseModel):
    status: str
    server_version: str | None = None

@router.post("/register", response_model=WorkerCreateResponse)
def register(body: WorkerCreate, db: Session = Depends(db_dependency)):
    worker, raw_token = worker_service.register_worker(db, body.name)
    return WorkerCreateResponse(
        worker_id=worker.id,
        name=worker.name,
        token=raw_token,
    )

@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(
    body: HeartbeatRequest,
    x_worker_token: str = Header(...),
    db: Session = Depends(db_dependency),
):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    worker_service.heartbeat(db, worker, body.version, body.os_type)
    return HeartbeatResponse(status="ok")

@router.get("/")
def list_workers(db: Session = Depends(db_dependency)):
    from hydra.db.models import Worker
    workers = db.query(Worker).all()
    return [
        {
            "id": w.id,
            "name": w.name,
            "status": w.status,
            "last_heartbeat": w.last_heartbeat,
            "current_version": w.current_version,
            "os_type": w.os_type,
        }
        for w in workers
    ]
```

- [ ] **Step 4: app.py에 Worker 라우터 등록**

`hydra/web/app.py`에 추가:

```python
from hydra.api.workers import router as workers_router
app.include_router(workers_router)
```

- [ ] **Step 5: Worker 토큰 생성 스크립트**

```python
"""Worker 연결 토큰 생성 스크립트.

사용법: python scripts/generate_worker_token.py --name "PC-1 (사무실)"
"""
import argparse
from hydra.db.session import SessionLocal
from hydra.services.worker_service import register_worker

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Worker 이름 (예: PC-1)")
    args = parser.parse_args()

    db = SessionLocal()
    worker, token = register_worker(db, args.name)
    db.close()

    print(f"Worker '{worker.name}' registered (ID: {worker.id})")
    print(f"Token: {token}")
    print("⚠️  이 토큰은 다시 표시되지 않습니다. 안전하게 보관하세요.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Worker API 테스트 작성 (tests/test_worker_api.py)**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hydra.db.models import Base
from hydra.web.app import app
from hydra.api.deps import db_dependency

@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_dependency] = override_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()

def test_register_worker(client):
    resp = client.post("/api/workers/register", json={"name": "PC-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "PC-1"
    assert "token" in data

def test_heartbeat(client):
    # 먼저 등록
    resp = client.post("/api/workers/register", json={"name": "PC-1"})
    token = resp.json()["token"]

    # heartbeat
    resp = client.post(
        "/api/workers/heartbeat",
        json={"version": "1.0.0", "os_type": "windows"},
        headers={"X-Worker-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_heartbeat_invalid_token(client):
    resp = client.post(
        "/api/workers/heartbeat",
        json={},
        headers={"X-Worker-Token": "invalid"},
    )
    assert resp.status_code == 401

def test_list_workers(client):
    client.post("/api/workers/register", json={"name": "PC-1"})
    client.post("/api/workers/register", json={"name": "PC-2"})
    resp = client.get("/api/workers/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
```

- [ ] **Step 7: 테스트 실행**

Run: `pytest tests/test_worker_api.py -v`
Expected: 4 tests PASSED

- [ ] **Step 8: Commit**

```bash
git add hydra/api/ hydra/services/ scripts/generate_worker_token.py tests/test_worker_api.py hydra/web/app.py
git commit -m "feat: Worker 등록/인증/heartbeat API"
```

---

### Task 7: 태스크 발행/수신 API

**Files:**
- Create: `hydra/services/task_service.py`
- Create: `hydra/api/tasks.py`
- Create: `tests/test_task_api.py`
- Modify: `hydra/web/app.py`

- [ ] **Step 1: 태스크 서비스 로직 (hydra/services/task_service.py)**

```python
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
from hydra.db.models import Task, ProfileLock, Worker

def fetch_tasks(db: Session, worker: Worker, limit: int = 5) -> list[Task]:
    """Worker에게 배정할 태스크 가져오기 (프로필 잠금 고려)."""
    now = datetime.utcnow()
    tasks = db.query(Task).filter(
        Task.status == "pending",
        Task.scheduled_at <= now,
    ).order_by(
        Task.priority.desc(),  # urgent > high > normal > low
        Task.created_at.asc(),
    ).limit(limit * 2).all()  # 잠금 충돌 여유분

    assigned = []
    for task in tasks:
        if len(assigned) >= limit:
            break

        # 프로필 잠금 확인
        if task.account_id:
            existing_lock = db.query(ProfileLock).filter(
                ProfileLock.account_id == task.account_id,
                ProfileLock.released_at.is_(None),
            ).first()
            if existing_lock and existing_lock.worker_id != worker.id:
                continue  # 다른 Worker가 잠금 중 → 건너뜀

        task.status = "assigned"
        task.worker_id = worker.id
        task.assigned_at = now
        assigned.append(task)

    db.commit()
    return assigned

def complete_task(db: Session, task_id: int, result: str = None):
    """태스크 완료 처리."""
    task = db.query(Task).get(task_id)
    if not task:
        return None
    task.status = "completed"
    task.completed_at = datetime.utcnow()
    if result:
        task.result = result

    # 프로필 잠금 해제
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.utcnow()

    db.commit()
    return task

def fail_task(db: Session, task_id: int, error: str):
    """태스크 실패 처리 (재시도 가능 시 재배정)."""
    task = db.query(Task).get(task_id)
    if not task:
        return None
    task.retry_count += 1
    if task.retry_count < task.max_retries:
        task.status = "pending"
        task.worker_id = None
        task.assigned_at = None
        task.error_message = error
    else:
        task.status = "failed"
        task.error_message = error
        task.completed_at = datetime.utcnow()

    # 프로필 잠금 해제
    if task.account_id:
        lock = db.query(ProfileLock).filter(
            ProfileLock.account_id == task.account_id,
            ProfileLock.released_at.is_(None),
        ).first()
        if lock:
            lock.released_at = datetime.utcnow()

    db.commit()
    return task
```

- [ ] **Step 2: Task API 엔드포인트 (hydra/api/tasks.py)**

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from hydra.api.deps import db_dependency
from hydra.services import worker_service, task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

class TaskResponse(BaseModel):
    id: int
    task_type: str
    priority: str
    payload: str | None
    account_id: int | None

class TaskCompleteRequest(BaseModel):
    task_id: int
    result: str | None = None

class TaskFailRequest(BaseModel):
    task_id: int
    error: str

@router.post("/fetch", response_model=list[TaskResponse])
def fetch_tasks(
    x_worker_token: str = Header(...),
    db: Session = Depends(db_dependency),
):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    tasks = task_service.fetch_tasks(db, worker)
    return [
        TaskResponse(
            id=t.id,
            task_type=t.task_type,
            priority=t.priority,
            payload=t.payload,
            account_id=t.account_id,
        )
        for t in tasks
    ]

@router.post("/complete")
def complete_task(
    body: TaskCompleteRequest,
    x_worker_token: str = Header(...),
    db: Session = Depends(db_dependency),
):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    task = task_service.complete_task(db, body.task_id, body.result)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task_id": task.id}

@router.post("/fail")
def fail_task(
    body: TaskFailRequest,
    x_worker_token: str = Header(...),
    db: Session = Depends(db_dependency),
):
    worker = worker_service.verify_token(db, x_worker_token)
    if not worker:
        raise HTTPException(status_code=401, detail="Invalid worker token")
    task = task_service.fail_task(db, body.task_id, body.error)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "task_id": task.id, "will_retry": task.status == "pending"}
```

- [ ] **Step 3: app.py에 Task 라우터 등록**

```python
from hydra.api.tasks import router as tasks_router
app.include_router(tasks_router)
```

- [ ] **Step 4: Task API 테스트 (tests/test_task_api.py)**

```python
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from hydra.db.models import Base, Task, Worker
from hydra.web.app import app
from hydra.api.deps import db_dependency
from hydra.services.worker_service import register_worker

@pytest.fixture
def client_with_worker():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_dependency] = override_db

    # Worker 등록 + 태스크 생성
    db = TestSession()
    worker, token = register_worker(db, "PC-1")
    task = Task(
        task_type="comment",
        priority="normal",
        status="pending",
        payload='{"text":"test"}',
        scheduled_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    task_id = task.id
    db.close()

    client = TestClient(app)
    yield client, token, task_id

    app.dependency_overrides.clear()
    engine.dispose()

def test_fetch_tasks(client_with_worker):
    client, token, _ = client_with_worker
    resp = client.post(
        "/api/tasks/fetch",
        headers={"X-Worker-Token": token},
    )
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "comment"

def test_complete_task(client_with_worker):
    client, token, task_id = client_with_worker
    # 먼저 fetch
    client.post("/api/tasks/fetch", headers={"X-Worker-Token": token})
    # 완료
    resp = client.post(
        "/api/tasks/complete",
        json={"task_id": task_id, "result": "done"},
        headers={"X-Worker-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

def test_fail_and_retry(client_with_worker):
    client, token, task_id = client_with_worker
    # fetch
    client.post("/api/tasks/fetch", headers={"X-Worker-Token": token})
    # 실패
    resp = client.post(
        "/api/tasks/fail",
        json={"task_id": task_id, "error": "captcha detected"},
        headers={"X-Worker-Token": token},
    )
    assert resp.status_code == 200
    assert resp.json()["will_retry"] is True  # max_retries=3, retry_count=1
```

- [ ] **Step 5: 테스트 실행**

Run: `pytest tests/test_task_api.py -v`
Expected: 3 tests PASSED

- [ ] **Step 6: Commit**

```bash
git add hydra/services/task_service.py hydra/api/tasks.py tests/test_task_api.py hydra/web/app.py
git commit -m "feat: 태스크 발행/수신/완료/실패 API + 프로필 잠금"
```

---

### Task 8: 기본 프리셋 A~J 시드 데이터

**Files:**
- Create: `scripts/seed_presets.py`

- [ ] **Step 1: 기존 시나리오 A~J를 프리셋으로 변환하는 시드 스크립트**

```python
"""기본 프리셋 A~J 시드 스크립트.

기존 hydra/core/scenarios.py의 시나리오 구조를 Preset 테이블에 삽입.
사용법: python scripts/seed_presets.py
"""
import json
from hydra.db.session import SessionLocal
from hydra.db.models import Preset

SYSTEM_PRESETS = [
    {
        "name": "씨앗 심기",
        "code": "A",
        "description": "단일 시드 댓글 + 좋아요 부스트",
        "steps": [
            {"step_number": 1, "role": "seed", "type": "comment", "tone": "자연스러운 후기", "target": "main", "like_count": 5, "delay_min": 0, "delay_max": 0},
        ],
    },
    {
        "name": "자연스러운 질문 유도",
        "code": "B",
        "description": "시드 + 질문자 + 답변 체인",
        "steps": [
            {"step_number": 1, "role": "seed", "type": "comment", "tone": "교육형", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "asker", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
            {"step_number": 3, "role": "seed", "type": "reply", "tone": "추천", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20},
        ],
    },
    {
        "name": "동조 여론 형성",
        "code": "C",
        "description": "시드 + 다수 동조 대댓글",
        "steps": [
            {"step_number": 1, "role": "seed", "type": "comment", "tone": "후기", "target": "main", "like_count": 20, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 30},
            {"step_number": 3, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 10, "delay_max": 40},
            {"step_number": 4, "role": "witness", "type": "reply", "tone": "경험담", "target": "step_1", "like_count": 5, "delay_min": 15, "delay_max": 45},
        ],
    },
    {
        "name": "비포애프터 경험담",
        "code": "D",
        "description": "경험자 시드 + 관심 + 추가 정보",
        "steps": [
            {"step_number": 1, "role": "witness", "type": "comment", "tone": "경험담", "target": "main", "like_count": 20, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "curious", "type": "reply", "tone": "호기심", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
            {"step_number": 3, "role": "witness", "type": "reply", "tone": "상세 정보", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20},
            {"step_number": 4, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 10, "delay_max": 35},
        ],
    },
    {
        "name": "슥 지나가기",
        "code": "E",
        "description": "짧은 캐주얼 단독 댓글",
        "steps": [
            {"step_number": 1, "role": "fan", "type": "comment", "tone": "캐주얼", "target": "main", "like_count": 5, "delay_min": 0, "delay_max": 0},
        ],
    },
    {
        "name": "정보형 교육",
        "code": "F",
        "description": "교육형 시드 + 질문 + 정보 제공",
        "steps": [
            {"step_number": 1, "role": "info", "type": "comment", "tone": "교육형", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "asker", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
            {"step_number": 3, "role": "info", "type": "reply", "tone": "정보 제공", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20},
        ],
    },
    {
        "name": "남의 댓글 올라타기",
        "code": "G",
        "description": "기존 인기 댓글에 대댓글로 진입",
        "steps": [
            {"step_number": 1, "role": "seed", "type": "reply", "tone": "공감+추천", "target": "existing_top", "like_count": 10, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "agree", "type": "reply", "tone": "동조", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 30},
        ],
    },
    {
        "name": "반박 → 중재",
        "code": "H",
        "description": "의견 대립 후 중재자가 브랜드 추천",
        "steps": [
            {"step_number": 1, "role": "seed", "type": "comment", "tone": "주장", "target": "main", "like_count": 10, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "asker", "type": "reply", "tone": "반박", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
            {"step_number": 3, "role": "witness", "type": "reply", "tone": "중재+추천", "target": "step_1", "like_count": 15, "delay_min": 10, "delay_max": 35},
            {"step_number": 4, "role": "agree", "type": "reply", "tone": "동조", "target": "step_3", "like_count": 0, "delay_min": 5, "delay_max": 25},
        ],
    },
    {
        "name": "간접 경험",
        "code": "I",
        "description": "지인 추천 형태의 간접 경험담",
        "steps": [
            {"step_number": 1, "role": "witness", "type": "comment", "tone": "간접 경험", "target": "main", "like_count": 15, "delay_min": 0, "delay_max": 0},
            {"step_number": 2, "role": "curious", "type": "reply", "tone": "질문", "target": "step_1", "like_count": 0, "delay_min": 5, "delay_max": 25},
            {"step_number": 3, "role": "witness", "type": "reply", "tone": "상세 답변", "target": "step_2", "like_count": 10, "delay_min": 5, "delay_max": 20},
        ],
    },
    {
        "name": "숏폼 전용",
        "code": "J",
        "description": "숏폼 영상용 짧은 단독 댓글",
        "steps": [
            {"step_number": 1, "role": "fan", "type": "comment", "tone": "짧은 반응", "target": "main", "like_count": 10, "delay_min": 0, "delay_max": 0},
        ],
    },
]

def seed():
    db = SessionLocal()
    for preset_data in SYSTEM_PRESETS:
        existing = db.query(Preset).filter(Preset.code == preset_data["code"]).first()
        if existing:
            print(f"  SKIP: {preset_data['code']} ({preset_data['name']}) — already exists")
            continue
        preset = Preset(
            name=preset_data["name"],
            code=preset_data["code"],
            is_system=True,
            description=preset_data["description"],
            steps=json.dumps(preset_data["steps"], ensure_ascii=False),
        )
        db.add(preset)
        print(f"  OK: {preset_data['code']} ({preset_data['name']})")
    db.commit()
    db.close()
    print("\nPreset seeding complete!")

if __name__ == "__main__":
    seed()
```

- [ ] **Step 2: 시드 스크립트 실행**

Run: `python scripts/seed_presets.py`
Expected: 10개 프리셋 A~J 삽입 완료

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_presets.py
git commit -m "feat: 기본 프리셋 A~J 시드 데이터"
```

---

### Task 9: 전체 통합 테스트 및 Docker 동작 확인

**Files:**
- No new files

- [ ] **Step 1: 전체 테스트 실행**

Run: `pytest tests/ -v`
Expected: 모든 테스트 PASSED (test_db_models 4개 + test_worker_api 4개 + test_task_api 3개 = 11개)

- [ ] **Step 2: Docker Compose 전체 실행**

Run: `docker-compose up -d`
Expected: db + server 컨테이너 정상 시작

- [ ] **Step 3: 헬스체크**

Run: `curl http://localhost:8000/`
Expected: 대시보드 HTML 응답

Run: `curl http://localhost:8000/api/workers/`
Expected: `[]` (빈 Worker 목록)

- [ ] **Step 4: Docker Compose 정리**

Run: `docker-compose down`

- [ ] **Step 5: 최종 Commit**

```bash
git add -A
git commit -m "feat: Phase 1 완료 — 기반 인프라 + DB (Docker, PostgreSQL, Worker/Task API)"
```

---

## Phase 1 완료 후 상태

이 Phase가 완료되면:

- ✅ Docker Compose로 VPS 배포 가능 (FastAPI + PostgreSQL)
- ✅ PostgreSQL로 전환 완료 (SQLite 폴백 유지)
- ✅ 기존 데이터 마이그레이션 가능
- ✅ Worker 등록/인증/heartbeat API 동작
- ✅ 태스크 발행/수신/완료/실패 API 동작
- ✅ 프로필 잠금 시스템 동작
- ✅ 기본 프리셋 A~J 시드
- ✅ 11개 테스트 통과

**다음 Phase:** `2026-04-16-02-server-api.md` — 캠페인, 브랜드, 타겟 영상, 분석 등 비즈니스 API
