"""워커 시크릿 로딩 (Task 32).

- Windows: C:\\hydra\\secrets.enc (DPAPI LocalMachine 암호화, 같은 PC 에서만 복호화)
- Mac/Linux dev: 프로젝트 루트 .env

setup.ps1 (Task 31) 이 enrollment 응답으로 받은 시크릿을 DPAPI 로 저장한다.
워커 런타임이 매 시작 시 이 모듈로 복호화 → 환경변수로 설정.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict

REQUIRED_KEYS = ("SERVER_URL", "WORKER_TOKEN")


def _secrets_enc_path() -> Path:
    """Windows DPAPI 암호화된 시크릿 파일 경로."""
    return Path(r"C:\hydra\secrets.enc")


def _dotenv_path() -> Path:
    """프로젝트 루트 .env (dev fallback)."""
    return Path(__file__).resolve().parent.parent / ".env"


def _parse_env_text(text: str) -> Dict[str, str]:
    """KEY=VALUE 줄 파싱. 주석/빈 줄 무시, = 여러 개면 첫 번째만 분할."""
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _load_dotenv(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    return _parse_env_text(path.read_text(encoding="utf-8"))


def _load_dpapi(path: Path) -> Dict[str, str]:  # pragma: no cover — Windows only
    """DPAPI 복호화 (Windows). pywin32 필수."""
    import win32crypt  # type: ignore[import-not-found]
    blob = path.read_bytes()
    _, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return _parse_env_text(decrypted.decode("utf-8"))


def load_secrets() -> Dict[str, str]:
    """시크릿 dict 반환. 플랫폼별 자동 분기 + os.environ 최종 override.

    Raises:
        RuntimeError: 소스가 없거나 REQUIRED_KEYS 중 누락.
    """
    result: Dict[str, str] = {}

    # 1. Windows → DPAPI 우선
    if sys.platform == "win32":
        p = _secrets_enc_path()
        if p.exists():
            result = _load_dpapi(p)

    # 2. .env fallback
    if not result:
        p = _dotenv_path()
        if p.exists():
            result = _load_dotenv(p)

    # 3. os.environ 최종 override (CI/테스트)
    for key in REQUIRED_KEYS:
        if key in os.environ and os.environ[key]:
            result[key] = os.environ[key]

    missing = [k for k in REQUIRED_KEYS if not result.get(k)]
    if missing or not result:
        source = "DPAPI (C:\\hydra\\secrets.enc)" if sys.platform == "win32" else ".env"
        raise RuntimeError(
            f"no secrets source found or missing keys {missing}. "
            f"Expected: {source}. "
            "Windows → 재설치 시 setup.ps1 실행 / dev → .env 파일 확인."
        )

    # 로드된 모든 키를 os.environ 에 주입 — pydantic settings / DRY-RUN 게이트 /
    # AdsPower 키 등이 동일 프로세스 내에서 환경변수로 읽히도록.
    # 이미 설정된 환경변수는 덮지 않음 (명시적 override 우선).
    for k, v in result.items():
        if v and not os.environ.get(k):
            os.environ[k] = v

    return result


def save_secrets_dpapi(secrets: Dict[str, str]) -> None:  # pragma: no cover
    """Windows 전용 — 시크릿을 DPAPI 로 저장 (setup.ps1 대체 경로용)."""
    if sys.platform != "win32":
        raise RuntimeError("DPAPI is Windows-only")
    import win32crypt  # type: ignore[import-not-found]
    text = "\n".join(f"{k}={v}" for k, v in secrets.items())
    blob = win32crypt.CryptProtectData(
        text.encode("utf-8"), "hydra-secrets", None, None, None, 0,
    )
    _secrets_enc_path().write_bytes(blob)
