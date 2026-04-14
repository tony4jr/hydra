"""IP Provider abstraction — pluggable proxy/IP rotation backends.

Spec Part 10 extension:
- AdbProvider: airplane mode toggle (original, default)
- ProxyApiProvider: HTTP proxy rotation API (Bright Data, Oxylabs, etc.)
- StaticProxyProvider: pre-configured proxy list rotation

Each provider implements rotate() → new IP, get_current_ip() → str.
"""

import asyncio
import random
from abc import ABC, abstractmethod

from hydra.core.logger import get_logger

log = get_logger("ip_provider")


class IpProvider(ABC):
    """Abstract IP rotation provider."""

    @abstractmethod
    async def rotate(self) -> str:
        """Rotate to a new IP. Returns the new IP address."""
        ...

    @abstractmethod
    async def get_current_ip(self) -> str:
        """Get the current public IP."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        ...


class AdbProvider(IpProvider):
    """IP rotation via ADB mobile data toggle.

    Uses `svc data disable/enable` to preserve Wi-Fi hotspot while
    forcing mobile network re-registration for a new IP.
    """

    def __init__(self, device_id: str, max_retries: int = 3):
        self.device_id = device_id
        self.max_retries = max_retries

    @property
    def name(self) -> str:
        return f"adb:{self.device_id}"

    async def _adb_shell(self, command: str) -> str:
        cmd = ["adb", "-s", self.device_id, "shell", command]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ADB error: {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def get_current_ip(self) -> str:
        result = await self._adb_shell("curl -s ifconfig.me")
        return result.strip()

    async def rotate(self) -> str:
        previous_ip = await self.get_current_ip()

        for attempt in range(1, self.max_retries + 1):
            log.info(f"[ADB] IP rotation attempt {attempt}/{self.max_retries} (current: {previous_ip})")

            await self._adb_shell("svc data disable")
            await asyncio.sleep(3)
            await self._adb_shell("svc data enable")

            wait = 12 * attempt
            await asyncio.sleep(wait)

            try:
                new_ip = await self.get_current_ip()
            except Exception as e:
                log.warning(f"[ADB] IP check failed attempt {attempt}: {e}")
                continue

            if new_ip and new_ip != previous_ip:
                log.info(f"[ADB] IP rotated: {previous_ip} → {new_ip}")
                return new_ip

            log.warning(f"[ADB] IP unchanged attempt {attempt}: {new_ip}")

        raise RuntimeError(f"ADB IP rotation failed after {self.max_retries} attempts")


class ProxyApiProvider(IpProvider):
    """IP rotation via proxy API service (Bright Data, Oxylabs, etc.).

    Uses a rotating proxy endpoint that gives a new IP per request.
    """

    def __init__(self, proxy_url: str, username: str = "", password: str = ""):
        self.proxy_url = proxy_url
        self.username = username
        self.password = password
        self._current_ip: str = ""

    @property
    def name(self) -> str:
        return f"proxy_api:{self.proxy_url[:30]}"

    async def get_current_ip(self) -> str:
        return self._current_ip or "unknown"

    async def rotate(self) -> str:
        import httpx

        auth = None
        if self.username:
            auth = (self.username, self.password)

        async with httpx.AsyncClient(
            proxies=self.proxy_url,
            auth=auth,
            timeout=30,
        ) as client:
            resp = await client.get("https://ifconfig.me")
            self._current_ip = resp.text.strip()

        log.info(f"[ProxyAPI] New IP: {self._current_ip}")
        return self._current_ip


class StaticProxyProvider(IpProvider):
    """IP rotation via a pre-configured list of proxy addresses.

    Cycles through proxies sequentially or randomly.
    """

    def __init__(self, proxies: list[str], randomize: bool = True):
        self.proxies = proxies
        self.randomize = randomize
        self._index = 0
        self._current_ip: str = ""
        self._current_proxy: str = ""

    @property
    def name(self) -> str:
        return f"static_proxy:{len(self.proxies)}_proxies"

    async def get_current_ip(self) -> str:
        return self._current_ip or "unknown"

    @property
    def current_proxy(self) -> str:
        """Get the current proxy URL for browser configuration."""
        return self._current_proxy

    async def rotate(self) -> str:
        import httpx

        if self.randomize:
            proxy = random.choice(self.proxies)
        else:
            proxy = self.proxies[self._index % len(self.proxies)]
            self._index += 1

        self._current_proxy = proxy

        try:
            async with httpx.AsyncClient(proxies=proxy, timeout=30) as client:
                resp = await client.get("https://ifconfig.me")
                self._current_ip = resp.text.strip()
        except Exception as e:
            log.warning(f"[StaticProxy] Failed with {proxy}: {e}")
            self._current_ip = "verify_failed"

        log.info(f"[StaticProxy] Proxy: {proxy} → IP: {self._current_ip}")
        return self._current_ip


# --- Provider Factory ---

_active_provider: IpProvider | None = None


def get_provider() -> IpProvider | None:
    """Get the currently active IP provider."""
    return _active_provider


def set_provider(provider: IpProvider):
    """Set the active IP provider."""
    global _active_provider
    _active_provider = provider
    log.info(f"IP provider set: {provider.name}")


def create_provider(provider_type: str, **kwargs) -> IpProvider:
    """Factory to create provider by type string.

    Args:
        provider_type: 'adb', 'proxy_api', 'static_proxy'
        **kwargs: Provider-specific arguments.
    """
    if provider_type == "adb":
        return AdbProvider(device_id=kwargs["device_id"], max_retries=kwargs.get("max_retries", 3))
    elif provider_type == "proxy_api":
        return ProxyApiProvider(
            proxy_url=kwargs["proxy_url"],
            username=kwargs.get("username", ""),
            password=kwargs.get("password", ""),
        )
    elif provider_type == "static_proxy":
        return StaticProxyProvider(
            proxies=kwargs["proxies"],
            randomize=kwargs.get("randomize", True),
        )
    else:
        raise ValueError(f"Unknown IP provider type: {provider_type}")
