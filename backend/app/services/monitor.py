import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from app.services.url_safety import resolve_public_addresses

Availability = Literal["up", "blocked", "down"]
MAX_ATTEMPTS = 3


@dataclass(slots=True)
class ProbeResult:
    is_up: bool
    availability: Availability
    status_code: int | None
    latency_ms: float | None
    error: str | None


def classify_response(
    status_code: int, expected_status: int
) -> tuple[Availability, str | None]:
    """Translate an HTTP result into an operational state.

    Access-control responses are tracked separately so a remote WAF or rate limit
    does not create a false outage in availability reporting.
    """
    if status_code == expected_status:
        return "up", None
    if status_code in {403, 429}:
        return (
            "blocked",
            f"Remote server blocked or rate-limited the probe (HTTP {status_code})",
        )
    return "down", f"Expected {expected_status}, received {status_code}"


async def probe_url(
    url: str,
    method: str,
    expected_status: int,
    timeout_seconds: int,
) -> ProbeResult:
    started = time.perf_counter()
    last_error = "Probe failed"
    headers = {
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "User-Agent": "PulseWatch/1.0 (+https://github.com/Adityagithubhack/pulsewatch)",
    }

    try:
        parsed = httpx.URL(url)
        await resolve_public_addresses(
            parsed.host, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except (OSError, ValueError) as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return ProbeResult(False, "down", None, latency_ms, str(exc)[:500])

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers=headers,
    ) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.request(method, url)
                availability, error = classify_response(
                    response.status_code, expected_status
                )

                # Retry only transient upstream failures. Client errors and WAF
                # responses are deterministic and should be reported immediately.
                if (
                    response.status_code >= 500
                    and availability == "down"
                    and attempt < MAX_ATTEMPTS - 1
                ):
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue

                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                return ProbeResult(
                    is_up=availability == "up",
                    availability=availability,
                    status_code=response.status_code,
                    latency_ms=latency_ms,
                    error=error,
                )
            except httpx.HTTPError as exc:
                last_error = str(exc)[:500]
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(0.25 * (2**attempt))

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return ProbeResult(False, "down", None, latency_ms, last_error)
