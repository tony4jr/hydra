"""Temporary email provider for Gmail signup recovery.

Primary: mail.tm — free REST API with token auth, Korean IP friendly.
Usage:
    async with TempMailClient() as mail:
        email = mail.address
        # ... signup flow uses this as recovery email ...
        verification_link = await mail.wait_for_verification_email(from_domain="google.com")

Each instance creates a fresh mailbox. Store the password/token in DB if you
need to retrieve the mailbox later.
"""

import asyncio
import random
import string
import httpx

from hydra.core.logger import get_logger

log = get_logger("temp_mail")

MAIL_TM_API = "https://api.mail.tm"


def _random_string(length: int = 12) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choices(alphabet, k=length))


class TempMailClient:
    """mail.tm temporary mailbox client."""

    def __init__(self):
        self.address: str = ""
        self.password: str = ""
        self.token: str = ""
        self.account_id: str = ""
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=MAIL_TM_API, timeout=30)
        await self._create_account()
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.aclose()

    async def _get_domain(self) -> str:
        resp = await self._client.get("/domains")
        data = resp.json()
        domains = data.get("hydra:member", [])
        if not domains:
            raise RuntimeError("mail.tm: no domains available")
        return domains[0]["domain"]

    async def _create_account(self):
        domain = await self._get_domain()
        local = _random_string(10)
        self.address = f"{local}@{domain}"
        self.password = _random_string(16) + "Aa1!"

        # Create account
        resp = await self._client.post(
            "/accounts",
            json={"address": self.address, "password": self.password},
        )
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"mail.tm account create failed: {resp.status_code} {resp.text}")
        self.account_id = resp.json().get("id", "")

        # Get auth token
        resp = await self._client.post(
            "/token",
            json={"address": self.address, "password": self.password},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"mail.tm token failed: {resp.status_code} {resp.text}")
        self.token = resp.json().get("token", "")
        self._client.headers["Authorization"] = f"Bearer {self.token}"

        log.info(f"Temp mailbox created: {self.address}")

    async def list_messages(self) -> list[dict]:
        resp = await self._client.get("/messages")
        return resp.json().get("hydra:member", [])

    async def get_message(self, msg_id: str) -> dict:
        resp = await self._client.get(f"/messages/{msg_id}")
        return resp.json()

    async def wait_for_message(
        self,
        from_contains: str = "",
        subject_contains: str = "",
        timeout_sec: int = 180,
        poll_interval: int = 5,
    ) -> dict | None:
        """Poll inbox until a matching message arrives or timeout."""
        elapsed = 0
        while elapsed < timeout_sec:
            messages = await self.list_messages()
            for msg in messages:
                sender = (msg.get("from", {}) or {}).get("address", "")
                subject = msg.get("subject", "")
                if from_contains and from_contains.lower() not in sender.lower():
                    continue
                if subject_contains and subject_contains.lower() not in subject.lower():
                    continue
                # Fetch full body
                return await self.get_message(msg["id"])
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        log.warning(f"No message matched within {timeout_sec}s (from={from_contains}, subject={subject_contains})")
        return None

    async def extract_verification_code(
        self,
        from_contains: str = "google",
        timeout_sec: int = 180,
    ) -> str | None:
        """Wait for Google verification email and extract 6-digit code."""
        import re
        msg = await self.wait_for_message(from_contains=from_contains, timeout_sec=timeout_sec)
        if not msg:
            return None
        body = msg.get("text") or ""
        # Google typically sends 6-digit codes
        match = re.search(r"\b(\d{6})\b", body)
        return match.group(1) if match else None
