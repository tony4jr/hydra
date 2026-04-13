"""2Captcha integration for solving reCAPTCHA.

Spec Part 11.2.1:
- YouTube may show captcha during login or comment
- 2Captcha API for automated solving
- 3 consecutive failures → account captcha_stuck
"""

import httpx
import asyncio

from hydra.core.config import settings
from hydra.core.logger import get_logger

log = get_logger("captcha")


class CaptchaSolver:
    """2Captcha solver for reCAPTCHA v2."""

    def __init__(self):
        self.api_key = settings.twocaptcha_api_key
        self.base_url = "https://2captcha.com"

    async def solve_recaptcha_v2(self, site_key: str, page_url: str, timeout: int = 120) -> str | None:
        """Solve a reCAPTCHA v2 challenge.

        Args:
            site_key: The reCAPTCHA site key from the page
            page_url: The URL where captcha appears

        Returns:
            Solution token string, or None on failure
        """
        if not self.api_key:
            log.error("2Captcha API key not configured")
            return None

        async with httpx.AsyncClient() as client:
            # Submit captcha
            try:
                resp = await client.post(f"{self.base_url}/in.php", data={
                    "key": self.api_key,
                    "method": "userrecaptcha",
                    "googlekey": site_key,
                    "pageurl": page_url,
                    "json": 1,
                })
                result = resp.json()

                if result.get("status") != 1:
                    log.error(f"2Captcha submit failed: {result}")
                    return None

                task_id = result["request"]
                log.info(f"Captcha submitted, task={task_id}")

            except Exception as e:
                log.error(f"2Captcha submit error: {e}")
                return None

            # Poll for result
            for _ in range(timeout // 5):
                await asyncio.sleep(5)

                try:
                    resp = await client.get(f"{self.base_url}/res.php", params={
                        "key": self.api_key,
                        "action": "get",
                        "id": task_id,
                        "json": 1,
                    })
                    result = resp.json()

                    if result.get("status") == 1:
                        token = result["request"]
                        log.info(f"Captcha solved, token length={len(token)}")
                        return token

                    if result.get("request") == "CAPCHA_NOT_READY":
                        continue

                    log.error(f"2Captcha error: {result}")
                    return None

                except Exception as e:
                    log.warning(f"2Captcha poll error: {e}")
                    continue

            log.error("Captcha solve timeout")
            return None

    async def get_balance(self) -> float:
        """Check 2Captcha account balance."""
        if not self.api_key:
            return 0.0
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{self.base_url}/res.php", params={
                "key": self.api_key,
                "action": "getbalance",
                "json": 1,
            })
            result = resp.json()
            return float(result.get("request", 0))


solver = CaptchaSolver()


async def solve_youtube_captcha(page, max_attempts: int = 3) -> bool:
    """Detect and solve captcha on current YouTube page.

    Returns True if solved or no captcha present.
    """
    for attempt in range(max_attempts):
        # Check for reCAPTCHA iframe
        captcha_frame = page.locator("iframe[src*='recaptcha']")
        if await captcha_frame.count() == 0:
            return True  # No captcha

        log.info(f"Captcha detected, solving (attempt {attempt+1})")

        # Extract site key
        try:
            src = await captcha_frame.first.get_attribute("src")
            # Parse site key from URL
            import re
            match = re.search(r"k=([A-Za-z0-9_-]+)", src)
            if not match:
                log.error("Could not extract reCAPTCHA site key")
                return False

            site_key = match.group(1)
            page_url = page.url

            token = await solver.solve_recaptcha_v2(site_key, page_url)
            if not token:
                continue

            # Inject solution token
            await page.evaluate(f"""
                document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                if (typeof ___grecaptcha_cfg !== 'undefined') {{
                    Object.entries(___grecaptcha_cfg.clients).forEach(([key, client]) => {{
                        Object.entries(client).forEach(([k, v]) => {{
                            if (v && v.callback) v.callback('{token}');
                        }});
                    }});
                }}
            """)

            await asyncio.sleep(2)

            # Check if captcha is gone
            if await captcha_frame.count() == 0:
                log.info("Captcha solved successfully")
                return True

        except Exception as e:
            log.error(f"Captcha solving error: {e}")
            continue

    log.error(f"Captcha not solved after {max_attempts} attempts")
    return False
