"""Field-level encryption for sensitive data (passwords, TOTP secrets, cookies).

Uses Fernet symmetric encryption. Key from HYDRA_ENCRYPTION_KEY env var.
If not set, auto-generates and saves to .env on first run.
"""

import os
import base64
from pathlib import Path

from cryptography.fernet import Fernet

from hydra.core.config import ROOT_DIR
from hydra.core.logger import get_logger

log = get_logger("crypto")

_cipher: Fernet | None = None


def _get_or_create_key() -> bytes:
    """Get encryption key from env, or generate and save one."""
    key = os.environ.get("HYDRA_ENCRYPTION_KEY")
    if key:
        return key.encode()

    # Check .env file
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("HYDRA_ENCRYPTION_KEY="):
                return line.split("=", 1)[1].strip().encode()

    # Generate new key
    new_key = Fernet.generate_key()
    log.warning("No encryption key found. Generating new key and saving to .env")

    with open(env_path, "a") as f:
        f.write(f"\n# Auto-generated encryption key (DO NOT SHARE)\nHYDRA_ENCRYPTION_KEY={new_key.decode()}\n")

    os.environ["HYDRA_ENCRYPTION_KEY"] = new_key.decode()
    return new_key


def _get_cipher() -> Fernet:
    global _cipher
    if _cipher is None:
        _cipher = Fernet(_get_or_create_key())
    return _cipher


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns base64-encoded ciphertext."""
    if not plaintext:
        return ""
    return _get_cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a string. Returns original plaintext."""
    if not ciphertext:
        return ""
    try:
        return _get_cipher().decrypt(ciphertext.encode()).decode()
    except Exception:
        # If decryption fails, assume it's already plaintext (migration)
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Check if a value looks like a Fernet token."""
    if not value:
        return False
    try:
        # Fernet tokens are base64 and start with 'gAAAAA'
        return value.startswith("gAAAAA") and len(value) > 50
    except Exception:
        return False
