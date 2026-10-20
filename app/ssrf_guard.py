"""SSRF protection for dashboard /probe proxy."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class SSRFBlockedError(ValueError):
    """Raised when a URL targets a disallowed host or scheme."""


def _is_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_probe_url(url: str) -> str:
    """Allow http/https only; block private, link-local, and loopback targets."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFBlockedError("Only http and https URLs are allowed for probe.")

    host = parsed.hostname
    if not host:
        raise SSRFBlockedError("URL must include a hostname.")

    lowered = host.lower()
    if lowered in ("localhost", "metadata.google.internal"):
        raise SSRFBlockedError(f"Host {host!r} is not allowed for probe.")

    try:
        addr = ipaddress.ip_address(host)
        if _is_blocked_ip(addr):
            raise SSRFBlockedError(f"IP {host} is in a blocked range.")
        return url
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve host {host!r}: {exc}") from exc

    for info in infos:
        resolved = info[4][0]
        try:
            addr = ipaddress.ip_address(resolved)
        except ValueError:
            continue
        if _is_blocked_ip(addr):
            raise SSRFBlockedError(
                f"Host {host!r} resolves to blocked address {resolved}."
            )

    return url