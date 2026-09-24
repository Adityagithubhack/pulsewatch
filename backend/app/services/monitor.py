import time
from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class ProbeResult:
    is_up: bool
    status_code: int | None
    latency_ms: float | None
    error: str | None


async def probe_url(
    url: str,
    method: str,
    expected_status: int,
    timeout_seconds: int,
) -> ProbeResult:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout_seconds,
            headers={"User-Agent": "PulseWatch/0.1"},
        ) as client:
            response = await client.request(method, url)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return ProbeResult(
            is_up=response.status_code == expected_status,
            status_code=response.status_code,
            latency_ms=latency_ms,
            error=None if response.status_code == expected_status else f"Expected {expected_status}",
        )
    except httpx.HTTPError as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return ProbeResult(False, None, latency_ms, str(exc)[:500])

