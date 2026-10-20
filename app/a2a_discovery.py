"""Active A2A Agent Card Discovery and Resolution Module."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.ssrf_guard import validate_probe_url

logger = logging.getLogger("x402_mcp.a2a_discovery")

A2A_X402_URI = "https://github.com/google-a2a/a2a-x402/v0.1"
AP2_URI = "https://github.com/google-agentic-commerce/ap2/v1"
DISCOVERY_PATHS = [
    "/.well-known/agent-card.json",
    "/.well-known/agent.json",
    "/.well-known/agents.json",
]


def normalize_target_urls(target: str) -> list[str]:
    """Sanitize target and return ordered list of discovery candidate URLs."""
    cleaned = target.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned

    validate_probe_url(cleaned)
    parsed = urlparse(cleaned)

    if parsed.path.endswith(".json"):
        return [cleaned]

    base = f"{parsed.scheme}://{parsed.netloc}"
    return [urljoin(base, path) for path in DISCOVERY_PATHS]


def parse_agent_card(data: dict[str, Any], source_url: str) -> dict[str, Any]:
    """Validate and normalize an A2A agent card payload."""
    capabilities = data.get("capabilities", {})
    extensions_raw = capabilities.get("extensions", [])

    extension_uris: list[str] = []
    for ext in extensions_raw:
        if isinstance(ext, dict):
            uri = ext.get("uri", "")
            if uri:
                extension_uris.append(uri)
        elif isinstance(ext, str):
            extension_uris.append(ext)

    has_x402 = any(
        A2A_X402_URI in uri or "a2a-x402" in uri.lower() for uri in extension_uris
    )
    has_ap2 = any(
        AP2_URI in uri or "ap2" in uri.lower() for uri in extension_uris
    )

    payments = data.get("payments", {})
    funding = data.get("funding", {})
    rails = payments.get("rails", []) if isinstance(payments, dict) else []
    first_rail_pay_to = rails[0].get("payTo") if rails and isinstance(rails[0], dict) else None
    pay_to = (
        funding.get("payTo")
        or payments.get("payTo")
        or first_rail_pay_to
        or data.get("pay_to")
    )

    if not rails and pay_to:
        rails = [{"network": "eip155:8453", "asset": "USDC", "payTo": pay_to}]

    raw_skills = data.get("skills", [])
    normalized_skills = []
    for skill in raw_skills:
        if isinstance(skill, dict):
            normalized_skills.append({
                "id": skill.get("id", skill.get("name", "unknown")),
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "tags": skill.get("tags", []),
                "price_usdc": str(skill.get("price_usdc") or skill.get("price") or ""),
                "network": skill.get("network", "eip155:8453"),
                "inputSchema": skill.get("inputSchema", {}),
            })

    return {
        "status": "valid",
        "resolved_url": source_url,
        "name": data.get("name", "Unnamed Agent"),
        "description": data.get("description", ""),
        "protocolVersion": data.get("protocolVersion", "1.0"),
        "extensions": extension_uris,
        "has_x402_extension": has_x402,
        "has_ap2_extension": has_ap2,
        "pay_to": pay_to,
        "payment_rails": rails,
        "skills_count": len(normalized_skills),
        "skills": normalized_skills,
        "supportedInterfaces": data.get("supportedInterfaces", ["mcp"]),
    }


async def resolve_agent_card(target: str, timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Discover, fetch, and normalize an external A2A Agent Card by domain or URL."""
    try:
        candidate_urls = normalize_target_urls(target)
    except Exception as exc:
        return {
            "status": "unresolved",
            "target": target,
            "error": f"Invalid target or SSRF check failed: {type(exc).__name__}: {str(exc)}",
            "candidates_probed": [],
        }

    last_error: str | None = None
    headers = {
        "User-Agent": "x402-mcp-resolver/1.0 (+https://github.com/kwizzlesurp10-ctrl/x402-mcp)",
        "Accept": "application/json, text/json",
    }

    async with httpx.AsyncClient(
        timeout=timeout_seconds, follow_redirects=True, max_redirects=3
    ) as client:
        for url in candidate_urls:
            try:
                validate_probe_url(url)
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        return parse_agent_card(data, str(resp.url))
                last_error = f"HTTP {resp.status_code} from {url}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)}"
                continue

    return {
        "status": "unresolved",
        "target": target,
        "error": last_error or "Agent Card not found at standard discovery endpoints.",
        "candidates_probed": candidate_urls,
    }
