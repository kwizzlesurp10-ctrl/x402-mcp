"""Comprehensive adversarial challenge test suite for get_agent_card and x402 resources.

Executed by m1_challenger_2 to stress-test:
1. get_agent_card tool across normal, boundary, empty, invalid, and adversarial inputs.
2. Quota isolation, rate limiting, and concurrency on get_agent_card.
3. x402://agent-card, x402://server-card, x402://tools-manifest, x402://pricing-table resource handlers.
4. Schema conformance against A2A Protocol v1.0 and MCP standard specifications.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

from app import mcp_server
from app.commerce import InMemoryQuotaStore, QuotaExceededError, quota_store
from app.config import settings
from app.manifest import build_mcp_manifest
from app.tools_registry import EXPECTED_TOOL_NAMES, TOOL_COUNT, TOOL_SPECS


class TestGetAgentCardToolAdversarial:
    """Adversarial stress tests for get_agent_card MCP tool."""

    @pytest.mark.asyncio
    async def test_get_agent_card_no_arguments_default(self) -> None:
        """Call get_agent_card with no arguments (default server card)."""
        raw = await mcp_server.get_agent_card()
        assert isinstance(raw, str), "Response must be a JSON string"

        payload = json.loads(raw)
        assert "data" in payload, "Envelope must have data field"
        assert "meta" in payload, "Envelope must have meta field"

        meta = payload["meta"]
        assert "agent_id" in meta
        assert "quota_remaining" in meta
        assert "calls_this_month" in meta

        data = payload["data"]
        assert "card" in data, "Default response must contain full card"
        assert "server_card" in data, "Default response must contain server_card"
        assert "tools_count" in data, "Default response must contain tools_count"
        assert data["tools_count"] == len(data["card"].get("skills", []))

        # Validate card schema
        card = data["card"]
        assert card["protocolVersion"] == "1.0"
        assert "skills" in card
        assert isinstance(card["skills"], list)
        assert len(card["skills"]) > 0

        # Validate server_card schema
        server_card = data["server_card"]
        assert "serverInfo" in server_card
        assert server_card["serverInfo"]["name"] == "io.github.kwizzlesurp10-ctrl/x402-mcp"
        assert server_card["capabilities"]["tools"] is True
        assert server_card["capabilities"]["resources"] is True
        assert server_card["capabilities"]["prompts"] is True
        assert len(server_card["tools"]) == TOOL_COUNT

    @pytest.mark.asyncio
    async def test_get_agent_card_valid_target_ids(self) -> None:
        """Test get_agent_card with valid skill IDs, names, and tags."""
        test_targets = [
            ("x402-agent-card", "Exact skill ID for agent card"),
            ("us-cities-catalog", "Exact skill ID for city catalog"),
            ("us-city-property-check", "Exact skill ID for property check"),
            ("us-rental-diligence-pack", "Exact skill ID for diligence pack"),
            ("property-check-mn", "Exact skill ID for Minneapolis"),
            ("property-check-sea", "Exact skill ID for Seattle"),
            ("property-check-chi", "Exact skill ID for Chicago"),
            ("catalog", "Tag matching"),
            ("compliance", "Tag matching"),
            ("open-data", "Tag matching"),
            ("rental", "Tag matching"),
            ("A2A Agent Card & Capabilities Inspector", "Full skill name matching"),
            ("US City Open-Data Compliance Catalog", "Full skill name matching"),
        ]

        for target_id, description in test_targets:
            raw = await mcp_server.get_agent_card(
                target_id=target_id, agent_id=f"test-agent-{target_id[:10]}"
            )
            payload = json.loads(raw)
            assert "data" in payload, f"Failed for target_id='{target_id}' ({description})"
            assert "meta" in payload, f"Missing meta for target_id='{target_id}'"

            data = payload["data"]
            assert data["target_id"] == target_id, (
                f"Expected target_id='{target_id}', got '{data.get('target_id')}'"
            )
            assert "skills" in data
            assert isinstance(data["skills"], list)
            assert len(data["skills"]) >= 1, (
                f"Expected matching skills for '{target_id}', got {data['skills']}"
            )
            assert "provider" in data
            assert "securitySchemes" in data
            assert "serverInfo" in data

    @pytest.mark.asyncio
    async def test_get_agent_card_invalid_and_nonexistent_targets(self) -> None:
        """Test get_agent_card with non-existent target IDs (verify graceful fallback to full card)."""
        nonexistent_targets = [
            "nonexistent_target_12345",
            "get_market_depth",
            "get_health",
            "unknown_skill_foo_bar_baz",
            "crypto_swap_v3",
        ]

        for target_id in nonexistent_targets:
            raw = await mcp_server.get_agent_card(
                target_id=target_id, agent_id="test-agent-invalid"
            )
            payload = json.loads(raw)
            assert "data" in payload, f"Failed gracefully on '{target_id}'"
            assert "meta" in payload
            data = payload["data"]
            # When target_id does not match any skill, it falls back to full card
            assert "card" in data, f"Expected fallback full card for '{target_id}'"
            assert "server_card" in data
            assert data["tools_count"] > 0

    @pytest.mark.asyncio
    async def test_get_agent_card_adversarial_inputs(self) -> None:
        """Stress-test get_agent_card with malicious, empty, unicode, and extreme inputs."""
        adversarial_inputs = [
            ("", "Empty string"),
            ("   ", "Whitespace only"),
            ("!@#$%^&*()_+-=[]{}|;':\",.<>?/`~", "Special characters"),
            ("🔥🚀🤖💡💎⚡", "Unicode emojis"),
            ("你好世界 / مرحبا بالعالم / Привет мир", "Multilingual UTF-8"),
            ("a" * 5000, "5,000 char long string"),
            ("\n\t\r\v\f", "Whitespace escape characters"),
            ("' OR '1'='1", "SQL injection attempt"),
            ("<script>alert('xss')</script>", "XSS script payload"),
            ("../../../etc/passwd", "Path traversal attempt"),
            ("{\"nested\": {\"json\": true}}", "JSON string input"),
            ("null", "String literal null"),
            ("true", "String literal true"),
            ("0", "String literal zero"),
        ]

        for adv_input, desc in adversarial_inputs:
            raw = await mcp_server.get_agent_card(
                target_id=adv_input, agent_id="test-adversary"
            )
            assert isinstance(raw, str), f"Must return string for {desc}"
            payload = json.loads(raw)
            assert "data" in payload, f"Must return valid envelope for {desc}"
            assert "meta" in payload, f"Must return meta for {desc}"

    @pytest.mark.asyncio
    async def test_get_agent_card_concurrent_load(self) -> None:
        """Concurrently invoke get_agent_card across 20 parallel coroutines."""
        agent_ids = [f"concurrent-agent-{i}" for i in range(20)]
        tasks = [
            mcp_server.get_agent_card(
                target_id="us-cities-catalog" if i % 2 == 0 else None,
                agent_id=agent_ids[i],
            )
            for i in range(20)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 20

        for i, res in enumerate(results):
            payload = json.loads(res)
            assert "data" in payload
            assert payload["meta"]["agent_id"] == agent_ids[i]

    @pytest.mark.asyncio
    async def test_get_agent_card_rate_limit_and_quota_exhaustion(self) -> None:
        """Exhaust rate limit for a specific agent and verify graceful error envelope."""
        temp_agent = f"rate-limit-test-{time.time()}"
        limit = settings.free_tier_rate_limit_per_min

        # Exhaust rate limit
        responses = []
        for _ in range(limit + 2):
            raw = await mcp_server.get_agent_card(agent_id=temp_agent)
            responses.append(json.loads(raw))

        # First `limit` calls should succeed
        for resp in responses[:limit]:
            assert "data" in resp
            assert resp["data"] is not None
            assert resp["meta"] is not None

        # Exceeded calls should return structured error envelope without unhandled exception
        exceeded_resp = responses[limit]
        assert "error" in exceeded_resp
        assert "rate_limit_exceeded" in str(exceeded_resp["error"])
        assert exceeded_resp["data"] is None
        assert exceeded_resp["meta"] is None


class TestFastMCPResourcesAdversarial:
    """Adversarial validation of FastMCP resources."""

    def test_all_four_resource_uris_registered(self) -> None:
        """Verify the 4 standard x402 resource URIs are registered in FastMCP."""
        resources = mcp_server.mcp._resource_manager._resources
        registered_uris = {str(r.uri) for r in resources.values()}

        expected = {
            "x402://agent-card",
            "x402://server-card",
            "x402://tools-manifest",
            "x402://pricing-table",
        }
        assert expected.issubset(registered_uris)
        assert len(resources) >= 4

    def test_agent_card_resource_standard_conformance(self) -> None:
        """Validate x402://agent-card against A2A Protocol v1.0 standard schema."""
        raw = mcp_server.get_agent_card_resource()
        assert isinstance(raw, str)
        card = json.loads(raw)

        # A2A top-level fields
        assert card.get("protocolVersion") == "1.0"
        assert isinstance(card.get("name"), str)
        assert isinstance(card.get("description"), str)
        assert isinstance(card.get("documentationUrl"), str)
        assert isinstance(card.get("provider"), dict)
        assert "organization" in card["provider"]
        assert "url" in card["provider"]

        # Capabilities
        assert isinstance(card.get("capabilities"), dict)
        assert card["capabilities"]["streaming"] is False
        assert card["capabilities"]["pushNotifications"] is False

        # Skills list
        assert "skills" in card
        assert isinstance(card["skills"], list)
        assert len(card["skills"]) >= 19, f"Expected at least 19 skills, got {len(card['skills'])}"

        # Validate each skill structure
        for skill in card["skills"]:
            assert isinstance(skill.get("id"), str) and len(skill["id"]) > 0
            assert isinstance(skill.get("name"), str) and len(skill["name"]) > 0
            assert isinstance(skill.get("description"), str) and len(skill["description"]) > 0
            assert isinstance(skill.get("tags"), list) and len(skill["tags"]) > 0
            assert isinstance(skill.get("examples"), list) and len(skill["examples"]) > 0
            assert isinstance(skill.get("inputModes"), list) and len(skill["inputModes"]) > 0
            assert isinstance(skill.get("outputModes"), list) and len(skill["outputModes"]) > 0

        # Security schemes
        assert "securitySchemes" in card
        assert "x402" in card["securitySchemes"]
        x402_sec = card["securitySchemes"]["x402"]
        assert x402_sec["type"] == "apiKey"
        assert x402_sec["name"] == "PAYMENT-SIGNATURE"

    def test_server_card_resource_standard_conformance(self) -> None:
        """Validate x402://server-card against MCP server card specification."""
        raw = mcp_server.get_server_card_resource()
        assert isinstance(raw, str)
        server_card = json.loads(raw)

        # Server Info
        assert "serverInfo" in server_card
        info = server_card["serverInfo"]
        assert info["name"] == "io.github.kwizzlesurp10-ctrl/x402-mcp"
        assert info["title"] == "x402 Micropayments MCP"
        assert info["version"] == "0.1.0"
        assert isinstance(info["description"], str)

        # Transport & Auth
        assert "transport" in server_card
        assert server_card["transport"]["type"] == "streamable-http"
        assert "authentication" in server_card
        assert server_card["authentication"]["type"] == "x402"
        assert server_card["authentication"]["scheme"] == "EIP-3009"
        assert server_card["authentication"]["asset"] == "USDC"

        # Capabilities
        assert server_card["capabilities"]["tools"] is True
        assert server_card["capabilities"]["resources"] is True
        assert server_card["capabilities"]["prompts"] is True

        # Tools list
        assert "tools" in server_card
        assert isinstance(server_card["tools"], list)
        assert len(server_card["tools"]) == TOOL_COUNT
        names = {t["name"] for t in server_card["tools"]}
        assert names == EXPECTED_TOOL_NAMES

    def test_tools_manifest_resource_standard_conformance(self) -> None:
        """Validate x402://tools-manifest against canonical MCP manifest specification."""
        raw = mcp_server.get_tools_manifest_resource()
        assert isinstance(raw, str)
        manifest = json.loads(raw)

        assert manifest["name"] == "x402-micropayments"
        assert manifest["protocol"] == "mcp"
        assert manifest["capabilities"]["tools"] is True
        assert manifest["capabilities"]["resources"] is True
        assert manifest["capabilities"]["prompts"] is True

        assert "tiers" in manifest
        assert manifest["tiers"]["free"]["monthly_quota"] == 500
        assert manifest["tiers"]["free"]["rate_limit_per_minute"] == 10

        assert len(manifest["tools"]) == TOOL_COUNT
        tool_names = {t["name"] for t in manifest["tools"]}
        assert tool_names == EXPECTED_TOOL_NAMES

    def test_pricing_table_resource_standard_conformance(self) -> None:
        """Validate x402://pricing-table schema completeness."""
        raw = mcp_server.get_pricing_table_resource()
        assert isinstance(raw, str)
        pricing = json.loads(raw)

        assert "free_tier" in pricing
        assert pricing["free_tier"]["monthly_quota"] == 500
        assert pricing["free_tier"]["rate_limit_per_minute"] == 10
        assert pricing["free_tier"]["price"] == "$0.00"

        assert "pro_tier" in pricing
        assert pricing["pro_tier"]["monthly_quota"] == 50000
        assert pricing["pro_tier"]["price_usd"] == "$29.00"

        assert "tool_credits" in pricing
        assert pricing["tool_credits"]["pack_size"] == 100
        assert "price_x402" in pricing["tool_credits"]

        assert "paid_endpoints" in pricing
        assert isinstance(pricing["paid_endpoints"], list)
        assert len(pricing["paid_endpoints"]) >= 1

        assert "payment_rails" in pricing
        assert pricing["payment_rails"]["stripe"]["primary"] is True
