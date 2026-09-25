import ipaddress
import asyncio
import socket
from urllib.parse import urlparse


def validate_monitor_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https")
    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".local"):
        raise ValueError("Local network targets are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return value
    if not address.is_global:
        raise ValueError("Private and reserved IP addresses are not allowed")
    return value


async def resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """Resolve a hostname and reject DNS rebinding to non-public networks."""
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    addresses = sorted({record[4][0] for record in records})
    if not addresses:
        raise ValueError("Target hostname did not resolve")
    for raw_address in addresses:
        if not ipaddress.ip_address(raw_address).is_global:
            raise ValueError("Target resolved to a private or reserved network")
    return addresses
