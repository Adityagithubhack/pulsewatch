import asyncio
import ssl
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.services.url_safety import resolve_public_addresses


async def inspect_endpoint(url: str) -> dict[str, object]:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.perf_counter()
    addresses = await resolve_public_addresses(hostname, port)
    dns_latency_ms = round((time.perf_counter() - started) * 1000, 2)

    result: dict[str, object] = {
        "hostname": hostname,
        "resolved_addresses": addresses,
        "dns_latency_ms": dns_latency_ms,
        "tls_enabled": parsed.scheme == "https",
        "tls_issuer": None,
        "tls_expires_at": None,
        "tls_days_remaining": None,
        "tls_status": "not_applicable",
    }
    if parsed.scheme != "https":
        return result

    context = ssl.create_default_context()
    _, writer = await asyncio.wait_for(
        asyncio.open_connection(hostname, port, ssl=context, server_hostname=hostname),
        timeout=10,
    )
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        certificate = ssl_object.getpeercert() if ssl_object else {}
        expires_raw = certificate.get("notAfter")
        expires_at = (
            datetime.strptime(expires_raw, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
            if expires_raw
            else None
        )
        days_remaining = (expires_at - datetime.now(UTC)).days if expires_at else None
        issuer_parts = certificate.get("issuer", [])
        issuer = ", ".join(
            f"{key}={value}" for group in issuer_parts for key, value in group
        )
        result.update(
            {
                "tls_issuer": issuer or None,
                "tls_expires_at": expires_at,
                "tls_days_remaining": days_remaining,
                "tls_status": "expired"
                if days_remaining is not None and days_remaining < 0
                else "warning"
                if days_remaining is not None and days_remaining < 30
                else "valid",
            }
        )
    finally:
        writer.close()
        await writer.wait_closed()
    return result
