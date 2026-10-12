"""Per-proxy, bounded cooldown for ChatGPT Responses SSE HTTP/2 resets."""
from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx


class ChatGPTSSETransportPolicy:
    """Keep healthy H2 fast; use the existing H1 pool after a known H2 reset."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._http1_until = 0.0

    @staticmethod
    def applies_to(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return (
            parsed.scheme == "https"
            and (host == "chatgpt.com" or host.endswith(".chatgpt.com"))
            and parsed.path.rstrip("/").endswith("/responses")
        )

    def prefers_http1(self, url: str) -> bool:
        return self.applies_to(url) and self._clock() < self._http1_until

    def record_reset(self, url: str, error: Exception) -> bool:
        if not self.applies_to(url) or not isinstance(
            error, (httpx.RemoteProtocolError, httpx.LocalProtocolError)
        ):
            return False
        # Do not demote ordinary H1 incomplete reads, timeouts, provider error
        # events, or WS service restarts. These are not HTTP/2 reset evidence.
        if not any(marker in str(error) for marker in ("StreamReset", "ConnectionTerminated")):
            return False
        self._http1_until = self._clock() + 300.0
        return True
