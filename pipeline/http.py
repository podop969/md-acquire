from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse
import random
import time

import requests

USER_AGENT = "md-acquire/0.1 (research; contact in config.yaml)"


class Client:
    """Throttled, retrying HTTP client with per-host pacing."""

    def __init__(self, min_interval: float = 1.0, timeout: int = 30, retries: int = 3):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_interval = min_interval
        self.timeout = timeout
        self.retries = retries
        self._last: dict[str, float] = defaultdict(float)

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        wait = self.min_interval - (time.time() - self._last[host])
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.time()

    def get(self, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            self._throttle(url)
            try:
                r = self.session.get(url, **kwargs)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"{r.status_code} from {url}", response=r)
                return r
            except requests.RequestException as exc:
                last_exc = exc
                if attempt + 1 < self.retries:
                    time.sleep((2 ** attempt) + random.random())
        raise last_exc  # type: ignore[misc]