"""VPS API payload → AccountSnapshot (Task 35).

워커는 로컬 DB 에 접근하지 않고 fetch 응답의 account_snapshot 만 사용한다.
password/totp_secret 은 VPS 가 이미 암호화한 상태로 보내므로, 여기서 복호화해
워커 메모리에서만 평문으로 보관한다 (디스크 저장 X).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from hydra.core import crypto


@dataclass
class AccountSnapshot:
    id: int
    gmail: str
    password: str  # 복호화된 평문 (메모리에만)
    adspower_profile_id: str
    recovery_email: Optional[str] = None
    persona: dict = field(default_factory=dict)
    totp_secret: Optional[str] = None  # 복호화된 평문
    status: str = "warmup"
    ipp_flagged: bool = False
    youtube_channel_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: dict, crypto_key: str = "") -> "AccountSnapshot":
        """fetch 응답 task dict 에서 AccountSnapshot 조립.

        crypto_key 인자는 시그니처 호환용 — 실제 복호화는 hydra.core.crypto 가
        env(HYDRA_ENCRYPTION_KEY) 기반으로 수행.
        """
        enc = payload.get("account_snapshot") or {}

        pwd_cipher = enc.get("encrypted_password")
        totp_cipher = enc.get("encrypted_totp_secret")

        persona_raw = enc.get("persona")
        if isinstance(persona_raw, str) and persona_raw:
            try:
                persona = json.loads(persona_raw)
            except json.JSONDecodeError:
                persona = {}
        elif isinstance(persona_raw, dict):
            persona = persona_raw
        else:
            persona = {}

        return cls(
            id=int(enc["id"]),
            gmail=enc["gmail"],
            password=crypto.decrypt(pwd_cipher) if pwd_cipher else "",
            adspower_profile_id=enc["adspower_profile_id"],
            recovery_email=enc.get("recovery_email"),
            persona=persona,
            totp_secret=crypto.decrypt(totp_cipher) if totp_cipher else None,
            status=enc.get("status", "warmup"),
            ipp_flagged=bool(enc.get("ipp_flagged", False)),
            youtube_channel_id=enc.get("youtube_channel_id"),
        )
