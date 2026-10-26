"""Async client for the EnBW e-mobility public API (+ PDOK geocoder).

Automatic calls (``auto=True``) are spread out (``spacing`` seconds between calls, even when many
stations share the same schedule) and protected by a circuit breaker: after too many consecutive
errors, or an HTTP 429, automatic calls are paused with an increasing delay. Manual calls and
config flow calls bypass pacing and the pause (but still update the health counters).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from math import atan2, cos, degrees, radians, sin, sqrt
from typing import Any

import aiohttp

from .const import (
    API_BACKOFF_BASE,
    API_BACKOFF_MAX,
    API_BASE,
    API_ORIGIN,
    PDOK_URL,
    RATE_LIMIT_DEFAULT_WAIT,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)

DEG_PER_M = 1 / 111_000


class EnbwApiError(Exception):
    """Generic error talking to the EnBW API."""


class EnbwAuthError(EnbwApiError):
    """API key rejected (401/403)."""


class EnbwNotFound(EnbwApiError):
    """Unknown station (404)."""


class EnbwBlocked(EnbwApiError):
    """Automatic call skipped because the API is paused (circuit open or key rejected)."""


class AddressNotFound(Exception):
    """PDOK found no address."""


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 6_371_000.0 * 2 * atan2(sqrt(a), sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, 0-360 (0 = north)."""
    p1, p2, dl = radians(lat1), radians(lat2), radians(lon2 - lon1)
    x = sin(dl) * cos(p2)
    y = cos(p1) * sin(p2) - sin(p1) * cos(p2) * cos(dl)
    return (degrees(atan2(x, y)) + 360) % 360


# Dutch compass names (user-facing) with arrows
_COMPASS = [
    ("N", "↑"),
    ("NO", "↗"),
    ("O", "→"),
    ("ZO", "↘"),
    ("Z", "↓"),
    ("ZW", "↙"),
    ("W", "←"),
    ("NW", "↖"),
]


def direction_label(bearing: float | None) -> str:
    """'↘ ZO': arrow before the compass direction from the search point to the station."""
    if bearing is None or bearing < 0:
        return ""
    name, arrow = _COMPASS[int(((bearing % 360) + 22.5) // 45) % 8]
    return f"{arrow} {name}"


def compass_label(bearing: float | None) -> str:
    """'ZW ↙': compass direction followed by the arrow."""
    if bearing is None or bearing < 0:
        return ""
    name, arrow = _COMPASS[int(((bearing % 360) + 22.5) // 45) % 8]
    return f"{name} {arrow}"


class EnbwApi:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        *,
        spacing: float = 0.0,
        max_errors: int = 10,
    ) -> None:
        self.session = session
        self._api_key = api_key
        self._spacing = spacing
        self._max_errors = max_errors
        self._pace_lock = asyncio.Lock()
        self._last_call = 0.0
        self.consecutive_errors = 0
        self._blocked_until = 0.0
        self.auth_failed = False
        self._was_outage = False
        # called with True/False when the API outage state changes (used for repair issues)
        self.on_outage_change: Callable[[bool], None] | None = None

    # ---- health
    @property
    def outage(self) -> bool:
        """True while automatic calls are paused because of repeated API errors."""
        return time.monotonic() < self._blocked_until

    @property
    def blocked(self) -> bool:
        """True when automatic calls must not be made (outage or rejected key)."""
        return self.auth_failed or self.outage

    @property
    def blocked_for(self) -> float:
        return max(self._blocked_until - time.monotonic(), 0.0)

    def _notify(self) -> None:
        outage = self.outage
        if outage != self._was_outage:
            self._was_outage = outage
            if self.on_outage_change:
                self.on_outage_change(outage)

    def _record_success(self) -> None:
        self.consecutive_errors = 0
        self._blocked_until = 0.0
        self._notify()

    def _record_failure(self, retry_after: float | None = None) -> None:
        self.consecutive_errors += 1
        wait = 0.0
        if retry_after is not None:
            wait = min(retry_after, API_BACKOFF_MAX)
        elif self.consecutive_errors >= self._max_errors:
            wait = min(API_BACKOFF_BASE * 2 ** (self.consecutive_errors - self._max_errors), API_BACKOFF_MAX)
        if wait:
            self._blocked_until = max(self._blocked_until, time.monotonic() + wait)
            _LOGGER.warning("EnBW API paused for %d s after %d consecutive errors", wait, self.consecutive_errors)
        self._notify()

    # ---- pacing
    async def _pace(self) -> None:
        if self._spacing <= 0:
            return
        async with self._pace_lock:  # FIFO: queued callers are released one by one
            wait = self._last_call + self._spacing - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Origin": API_ORIGIN,
            "Referer": f"{API_ORIGIN}/",
            "Ocp-Apim-Subscription-Key": self._api_key,
        }

    def _raise_if_blocked(self) -> None:
        if self.auth_failed:
            raise EnbwBlocked("API key rejected")
        if self.outage:
            raise EnbwBlocked(f"API paused for another {self.blocked_for:.0f} s")

    async def _get(self, path: str, params: dict[str, Any] | None = None, *, auto: bool = False) -> Any:
        if auto:
            self._raise_if_blocked()
            await self._pace()
            self._raise_if_blocked()  # the state may have changed while waiting
        try:
            async with self.session.get(
                f"{API_BASE}/{path}",
                params=params,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as r:
                if r.status in (401, 403):
                    self.auth_failed = True
                    raise EnbwAuthError(f"API key rejected (HTTP {r.status})")
                if r.status == 404:
                    self._record_success()  # a valid answer: the API itself is healthy
                    raise EnbwNotFound(path)
                if r.status == 429:
                    retry = r.headers.get("Retry-After", "")
                    self._record_failure(float(retry) if retry.isdigit() else RATE_LIMIT_DEFAULT_WAIT)
                    raise EnbwApiError("Rate limited by EnBW (HTTP 429)")
                if r.status >= 500:
                    self._record_failure()
                    raise EnbwApiError(f"Server error (HTTP {r.status})")
                if r.status >= 400:
                    raise EnbwApiError(f"Unexpected response (HTTP {r.status})")
                data = await r.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            self._record_failure()
            raise EnbwApiError(f"Communication error with EnBW: {err}") from err
        self._record_success()
        return data

    async def async_list(self, lat: float, lon: float, radius_m: float) -> list[dict[str, Any]]:
        """Stations in a bounding box around the point (never smaller than the radius)."""
        half_lat = radius_m * DEG_PER_M
        half_lon = half_lat / max(cos(radians(lat)), 0.01)
        data = await self._get(
            "chargestations",
            {
                "fromLat": f"{lat - half_lat:.6f}",
                "toLat": f"{lat + half_lat:.6f}",
                "fromLon": f"{lon - half_lon:.6f}",
                "toLon": f"{lon + half_lon:.6f}",
                "grouping": "false",
                "groupingDivisor": "15",
            },
        )
        if not isinstance(data, list):
            return []
        return [x for x in data if isinstance(x, dict)]

    async def async_check_key(self, lat: float, lon: float) -> None:
        """Raise unless the key is accepted (small area search; there is no dedicated endpoint)."""
        await self.async_list(lat, lon, 5000)

    async def async_detail(self, station_id: str, *, auto: bool = False) -> dict[str, Any]:
        data = await self._get(f"chargestations/{station_id}", auto=auto)
        if not isinstance(data, dict):
            raise EnbwApiError("Unexpected response for station")
        return data

    async def async_details(self, ids: list[str]) -> dict[str, dict[str, Any] | BaseException]:
        """Fetch several stations (max 5 in parallel); errors are returned, not raised."""
        sem = asyncio.Semaphore(5)

        async def one(sid: str) -> Any:
            async with sem:
                return await self.async_detail(sid)

        results = await asyncio.gather(*(one(i) for i in ids), return_exceptions=True)
        return dict(zip(ids, results, strict=True))

    async def async_geocode(self, address: str) -> tuple[float, float, str]:
        """Place name/address -> (lat, lon, display name).

        A plain place name first searches populated places only; otherwise the municipality
        (with its centre in the woods) or a street elsewhere could win. With a house number or
        comma, all types are searched.
        """
        specific = any(ch.isdigit() for ch in address) or "," in address
        docs: list[dict[str, Any]] = []
        for fq in [None] if specific else ["type:woonplaats", None]:
            params: dict[str, Any] = {"q": address, "rows": 5, "fl": "weergavenaam,centroide_ll,type"}
            if fq:
                params["fq"] = fq
            try:
                async with self.session.get(
                    PDOK_URL,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=25),
                ) as r:
                    r.raise_for_status()
                    data = await r.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise EnbwApiError(str(err)) from err
            docs = data.get("response", {}).get("docs", [])
            if docs:
                break
        if not docs:
            raise AddressNotFound(address)
        doc = docs[0]  # PDOK sorts by relevance
        point = doc.get("centroide_ll", "")
        if not point.startswith("POINT("):
            raise AddressNotFound(address)
        lon, lat = map(float, point[6:-1].split())
        return lat, lon, doc.get("weergavenaam", address)
