"""Tests for Reference Buyer Agent (examples/reference_buyer_agent.py)."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest

from app.main import app
from examples.reference_buyer_agent import (
    build_authorization,
    discover_services,
    dispatch_receipt_to_mailrail,
    encode_b64_json,
    parse_b64_json,
    probe_service_challenge,
    run_buyer_workflow,
)

test_client = TestClient(app)


def test_b64_json_roundtrip() -> None:
    payload = {"hello": "world", "price": 10000, "network": "eip155:8453"}
    encoded = encode_b64_json(payload)
    decoded = parse_b64_json(encoded)
    assert decoded == payload


def test_discover_services_with_agentic_market() -> None:
    manifest = discover_services("http://testserver", client=test_client)
    assert "schema_version" in manifest
    assert "services" in manifest
    assert "settlement" in manifest
    assert manifest["settlement"]["protocol"] == "x402"


def test_probe_free_endpoint() -> None:
    status, body, header = probe_service_challenge("http://testserver/mn/property-check/sample", client=test_client)
    assert status == 200
    assert body is not None
    assert "sample_address" in body


def test_probe_402_paid_endpoint() -> None:
    status, challenge, header = probe_service_challenge("http://testserver/base/tx-decision", client=test_client)
    assert status == 402
    assert challenge is not None
    assert "error" in challenge or "accepts" in challenge


def test_build_authorization_payload() -> None:
    mock_challenge = {
        "payTo": "0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e",
        "amount": 10000,
        "network": "eip155:8453",
    }
    sig_b64 = build_authorization(mock_challenge, buyer_address="0xTestBuyer")
    parsed = parse_b64_json(sig_b64)
    assert parsed["from"] == "0xTestBuyer"
    assert parsed["to"] == "0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e"
    assert parsed["value"] == "10000"
    assert "validBefore" in parsed


def test_dispatch_receipt_to_mailrail() -> None:
    receipt = {
        "service": "base-tx-decision",
        "tx_hash": "0xabcdef1234567890",
        "amount": 10000,
        "status": "settled",
    }
    resp = dispatch_receipt_to_mailrail("http://testserver", receipt, client=test_client)
    assert resp.get("status") in ("accepted", "received") or "inbound_id" in resp or "mail_id" in resp


def test_run_buyer_workflow_dry_run() -> None:
    result = run_buyer_workflow(
        base_url="http://testserver",
        service_key="base-tx-decision",
        dry_run=True,
        client=test_client,
    )
    assert result["success"] is True
    assert result["dry_run"] is True
    assert "challenge" in result
    assert "simulated_receipt" in result
    assert "mailrail_dispatch" in result
