"""Goal verification runner — saves evidence to scratch directory."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    os.environ.get("GOAL_SCRATCH", str(Path(tempfile.gettempdir()) / "x402-mcp-evidence"))
)
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def run_pytest() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log = SCRATCH / "pytest.log"
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    body = proc.stdout + proc.stderr
    log.write_text(body + f"\nEXIT_CODE={proc.returncode}\n", encoding="utf-8")
    return proc.returncode


def run_launch_check() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log = SCRATCH / "launch.log"
    lines: list[str] = []

    import httpx

    for boot in (1, 2):
        proc = subprocess.Popen(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8402",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(3)
            health = httpx.get("http://127.0.0.1:8402/health", timeout=10)
            manifest = httpx.get("http://127.0.0.1:8402/.well-known/mcp", timeout=10)
            upgrade = httpx.get("http://127.0.0.1:8402/upgrade", timeout=10)
            lines.append(f"=== boot {boot} ===")
            lines.append(f"health_status={health.status_code}")
            lines.append(f"health_body={health.text}")
            lines.append(f"manifest_status={manifest.status_code}")
            lines.append(f"manifest_body={manifest.text}")
            lines.append(f"upgrade_status={upgrade.status_code}")
            lines.append(f"upgrade_body={upgrade.text}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    log.write_text("\n".join(lines), encoding="utf-8")
    joined = "".join(lines)
    ok = (
        "status" in joined
        and "x402-micropayments" in joined
        and "upgrade_status=200" in joined
        and '"stripe"' in joined
        and "x402_coinbase" in joined
    )
    return 0 if ok else 1


async def run_tool_smoke() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from app.mcp_server import get_supported_networks

    raw = await get_supported_networks(agent_id="goal-verifier")
    out = SCRATCH / "tool_smoke.json"
    out.write_text(raw, encoding="utf-8")
    payload = json.loads(raw)
    ok = "data" in payload and "meta" in payload and "quota_remaining" in payload["meta"]
    return 0 if ok else 1


def _local_402_url() -> str:
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler402(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(402)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler402)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}/paid"


async def run_stdio_smoke() -> int:
    """Stdio buyer tool: get_payment_requirements against local 402 server."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    probe_url = _local_402_url()
    server_params = StdioServerParameters(
        command=str(PYTHON),
        args=[str(ROOT / "run_stdio.py")],
        cwd=str(ROOT),
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_payment_requirements",
                {"url": probe_url, "agent_id": "stdio-buyer-verifier"},
            )
    out = SCRATCH / "stdio_tool_smoke.json"
    text = result.content[0].text if result.content else "{}"
    out.write_text(text, encoding="utf-8")
    payload = json.loads(text)
    ok = (
        "meta" in payload
        and "data" in payload
        and payload["data"].get("status_code") == 402
    )
    return 0 if ok else 1


def run_pay_fetch_evidence() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    log = SCRATCH / "pay_fetch.log"
    if not (ROOT / "tests" / "test_pay_and_fetch_e2e.py").exists():
        return
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", "tests/test_pay_and_fetch_e2e.py", "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    log.write_text(proc.stdout + proc.stderr, encoding="utf-8")


async def run_pro_stdio_evidence() -> None:
    """Evidence: stdio MCP transport for pro/credits tools (not direct imports)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "X402_PAY_TO_ADDRESS": "0xEvidencePayTo000000000000000001"}
    server_params = StdioServerParameters(
        command=str(PYTHON),
        args=[str(ROOT / "run_stdio.py")],
        cwd=str(ROOT),
        env=env,
    )
    out = SCRATCH / "stdio_pro_smoke.json"
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_pro_upgrade_requirements", {})
    text = result.content[0].text if result.content else "{}"
    out.write_text(text, encoding="utf-8")


def _stdio_pro_agent_id_ok() -> bool:
    path = SCRATCH / "stdio_pro_smoke.json"
    if not path.exists():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        payload.get("meta", {}).get("agent_id")
        == payload.get("data", {}).get("agent_id")
    )


def run_stripe_init_smoke() -> int:
    """Stripe checkout initiation via shipped HTTP route (mocked Stripe API)."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    from unittest.mock import MagicMock, patch

    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    out = SCRATCH / "stripe_init_smoke.json"
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/c/pay/cs_smoke"
    mock_session.id = "cs_smoke"

    old_key = settings.stripe_secret_key
    settings.stripe_secret_key = "sk_test_smoke"
    try:
        with patch("stripe.checkout.Session.create", return_value=mock_session):
            client = TestClient(app)
            response = client.post(
                "/stripe/checkout",
                json={
                    "agent_id": "stripe-smoke-agent",
                    "purpose": "pro_tier_upgrade",
                },
            )
        out.write_text(response.text, encoding="utf-8")
        payload = response.json()
        ok = (
            response.status_code == 200
            and payload.get("checkout_url")
            and payload.get("agent_id") == "stripe-smoke-agent"
            and payload.get("purpose") == "pro_tier_upgrade"
        )
        return 0 if ok else 1
    finally:
        settings.stripe_secret_key = old_key


def run_stripe_webhook_smoke() -> int:
    """Signed webhook fixture → 2xx + fulfillment; bad sig → 4xx."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from app.commerce import InMemoryQuotaStore
    from app.config import settings
    from app.main import app
    from app import stripe_payments

    log = SCRATCH / "stripe_webhook_smoke.log"
    lines: list[str] = []
    webhook_secret = "whsec_smoke_test_secret_12345"

    store = InMemoryQuotaStore()
    old_secret = settings.stripe_webhook_secret
    settings.stripe_webhook_secret = webhook_secret
    import app.main as main_mod
    import app.stripe_payments as sp_mod

    old_store = main_mod.quota_store
    main_mod.quota_store = store
    sp_mod.quota_store = store
    try:
        payload = json.dumps(
            {
                "id": "evt_smoke_pro",
                "object": "event",
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": "cs_smoke_session",
                        "payment_intent": "pi_smoke_pro",
                        "metadata": {
                            "agent_id": "stripe-webhook-smoke",
                            "purpose": "pro_tier_upgrade",
                        }
                    }
                },
            }
        ).encode()
        sig = stripe_payments.build_test_webhook_signature(payload, webhook_secret)
        client = TestClient(app)
        good = client.post(
            "/stripe/webhook",
            content=payload,
            headers={"Stripe-Signature": sig},
        )
        bad = client.post(
            "/stripe/webhook",
            content=payload,
            headers={"Stripe-Signature": "invalid"},
        )
        tier = client.get("/quota/stripe-webhook-smoke")
        lines.append(f"good_status={good.status_code}")
        lines.append(f"good_body={good.text}")
        lines.append(f"bad_status={bad.status_code}")
        lines.append(f"tier_body={tier.text}")
        ok = (
            good.status_code == 200
            and bad.status_code == 400
            and tier.json().get("meta", {}).get("tier") == "pro"
        )
        return 0 if ok else 1
    finally:
        settings.stripe_webhook_secret = old_secret
        main_mod.quota_store = old_store
        sp_mod.quota_store = old_store
        log.write_text("\n".join(lines), encoding="utf-8")


def run_x402_preserved_evidence() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from app.models import BuildSellerRequirementsInput
    from app import x402_services

    log = SCRATCH / "x402_preserved.log"
    env_pay_to = os.environ.get("X402_PAY_TO_ADDRESS")
    if env_pay_to:
        try:
            result = x402_services.build_pro_upgrade_requirements("preserve-agent")
            log.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception as exc:
            log.write_text(f"error: {exc}\n", encoding="utf-8")
    else:
        try:
            x402_services.build_pro_upgrade_requirements("preserve-agent")
        except ValueError as exc:
            log.write_text(f"x402_preserved_skip: {exc}\n", encoding="utf-8")

    skip_log = SCRATCH / "stripe_skip.log"
    if not os.environ.get("STRIPE_SECRET_KEY"):
        skip_log.write_text(
            "STRIPE_SECRET_KEY not set; live Stripe CLI trigger skipped\n",
            encoding="utf-8",
        )


def run_seller_evidence() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    from app.models import BuildSellerRequirementsInput
    from app import x402_services

    log = SCRATCH / "seller_skip.log"
    try:
        x402_services.build_seller_requirements(BuildSellerRequirementsInput())
    except ValueError as exc:
        log.write_text(f"expected_skip: {exc}\n", encoding="utf-8")

    pro_log = SCRATCH / "pro_upgrade.log"
    try:
        result = x402_services.build_pro_upgrade_requirements("evidence-agent")
        pro_log.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except ValueError as exc:
        pro_log.write_text(f"expected_skip: {exc}\n", encoding="utf-8")


def main() -> int:
    import time as _time

    global time
    time = _time

    codes = []
    codes.append(run_pytest())
    codes.append(run_launch_check())
    codes.append(asyncio.run(run_tool_smoke()))
    codes.append(asyncio.run(run_stdio_smoke()))
    asyncio.run(run_pro_stdio_evidence())
    pro_id_ok = _stdio_pro_agent_id_ok()
    codes.append(run_stripe_init_smoke())
    codes.append(run_stripe_webhook_smoke())
    run_pay_fetch_evidence()
    run_seller_evidence()
    run_x402_preserved_evidence()
    summary = SCRATCH / "verify_summary.txt"
    summary.write_text(
        "\n".join(
            [
                f"pytest={codes[0]}",
                f"launch={codes[1]}",
                f"tool_smoke={codes[2]}",
                f"stdio_smoke={codes[3]}",
                f"stdio_pro_agent_id_match={0 if pro_id_ok else 1}",
                f"stripe_init={codes[4]}",
                f"stripe_webhook={codes[5]}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if not pro_id_ok:
        codes.append(1)
    return max(codes)


if __name__ == "__main__":
    raise SystemExit(main())