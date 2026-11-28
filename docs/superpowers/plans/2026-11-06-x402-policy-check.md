# x402.policy_check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

I'm using the writing-plans skill to create the implementation plan.

**Goal:** Ship `x402.policy_check` as a paid offline buyer payment-policy consistency inspector with one shared evaluator for HTTP `POST /x402/policy-check`, MCP tool `x402.policy_check`, and A2A skill `buyer-payment-policy-check`, without external URL fetch for the inspected merchant and without using the caller-supplied inspected header as this service's payment auth.

**Architecture:** Add `app/policy_check.py` containing pure `evaluate_policy(...)` (decode via `decode_payment_required_header`, per-accept evaluation, verdict + digests) plus `build_payment_required_header` / `verify_and_settle` for **this** product only, mirroring `app/diligence_pack.py` and `app/diligence_routes.py` patterns. Wire HTTP in `app/main.py` (or `app/policy_check_routes.py` + include), MCP in `app/mcp_server.py` + `app/tools_registry.py`, A2A in `app/a2a_rpc.py` `_skill_bindings()` and `app/agent_surface.py` agent card. Idempotency and delivery receipts align with `app/mcp_x402_payment.py` + `app/mcp_settlement_store.py` (challenge fingerprint for **server** challenge, never for inspected blob). Discovery: `paid_resources()`, `openapi_spec.output_examples()`, `tighten()` keep allowlist behavior.

**Tech Stack:** Python 3.x, FastAPI, Pydantic v2, pinned `x402` PyPI package (see `pyproject.toml`), Redis when `REDIS_URL` set (`settings.redis_url` / `settings.mcp_commerce_redis_strict` patterns), pytest.

## Global Constraints

- **No new unmanaged dependencies** — only existing `pyproject.toml` deps; no new npm/TS packages or server-side packages without operator approval.
- **`POLICY_CHECK_ENABLED`** default **`false`**; when false, paid surfaces return **503** `feature_disabled` (or consistent with other gated products); tests enable explicitly.
- **Default analysis fee** configurable via new `settings.policy_check_price: str = "$0.01"` in `app/config.py`; floor respects CDP **$0.001 USDC** minimum if enforced elsewhere; document as hypothesis not validated economics.
- **No HTTP outbound** to merchant URLs in policy-check code paths.
- **Never** verify settlement for **this** service using caller-supplied `payment_required_header` (inspected); only server-built challenge from `build_*_requirements` / `build_payment_required_header` (see `app/commerce_payment.py` docstring lines 3–7).
- **Integer amounts only** for policy comparison: `int(str(accept.amount))` after validate non-empty decimal digit string; reject float/symbol shortcuts.
- **EVM** addresses: lowercase `0x` + 40 hex; **Solana**: case-sensitive string equality (no lowercasing).
- **Bounded inputs:** max raw header length 65536, max JSON after decode 262144, max `len(accepts)` 16 (constants in `policy_check.py` with env overrides acceptable).
- **Product id constant** e.g. `policy-check-analysis` for `demand.record_challenge`, ledger, and skill `product_id` binding.
- **Do not modify** merged PR **#787** / **#790** contents; implement forward-only on current master.
- **Mocks in tests only** — fakeredis or existing test doubles; production paths never return fake verdicts as real.

---

## File map (create / modify)

| File | Role |
|------|------|
| `app/policy_check.py` | `PolicyCheckRequest`, `BuyerPolicy`, `evaluate_policy`, `input_digest_sha256`, `analysis_receipt_digest`, `PRODUCT_ID`, `RESOURCE_DESCRIPTION`, `build_payment_required_header`, `verify_and_settle` |
| `app/policy_check_routes.py` | FastAPI router: unpaid 402 + paid POST (validate-then-charge), `Idempotency-Key` header, rate limits consistent with neighbors |
| `app/main.py` | `app.include_router(policy_check_routes.router, ...)` |
| `app/config.py` | `policy_check_enabled`, `policy_check_price`, optional `policy_check_max_accepts` |
| `app/agent_surface.py` | Entry in `paid_resources()`; `agent_card` skill block |
| `app/openapi_spec.py` | `output_examples["/x402/policy-check"]`, ensure path in `paid_paths()` via `paid_resources()` |
| `app/mcp_server.py` | Register `x402.policy_check` with payment wrapper pattern analogous to paid city/commerce tools |
| `app/tools_registry.py` | `TOOL_SPECS` entry for `x402.policy_check` |
| `app/a2a_rpc.py` | `_skill_bindings["buyer-payment-policy-check"]` |
| `tests/test_policy_check_evaluate.py` | Pure evaluator matrix |
| `tests/test_policy_check_http.py` | 402 unpaid, 200 paid once, idempotency conflict |
| `tests/test_policy_check_mcp.py` | PaymentRequired then success meta |
| `tests/test_policy_check_a2a.py` | Skill execute parity |
| `README.md` or `docs/` | Buyer-facing caveat: offline consistency only; not settlement proof |

---

### Task 1: Evaluator core (pure, TDD)

**Files:**
- Create: `app/policy_check.py` (evaluate-only slice first)
- Create: `tests/test_policy_check_evaluate.py`

**Interfaces:**
- Consumes: `from x402.http import decode_payment_required_header`; `PaymentRequirements` / `PaymentRequired` from SDK
- Produces: `def evaluate_policy(*, payment_required_header: str, policy: BuyerPolicy, request_digest: RequestDigest | None) -> PolicyCheckResult`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_policy_check_evaluate.py
import pytest
from x402.http import encode_payment_required_header
from x402.schemas import PaymentRequired, PaymentRequirements

from app.policy_check import BuyerPolicy, evaluate_policy


def _minimal_valid_header() -> str:
    """Deterministic challenge for unit tests — same pattern as examples/x402_gate.py."""
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
        description="policy-check test",
    )
    pr = PaymentRequired(x402_version=2, accepts=[req], error="test")
    return encode_payment_required_header(pr)


def test_decode_error_inconclusive():
    out = evaluate_policy(
        payment_required_header="not-valid-base64@@@",
        policy=BuyerPolicy(),
        request_digest=None,
    )
    assert out.verdict == "inconclusive"
    assert any(r.get("code") == "decode_error" for r in out.top_reasons)


def test_per_accept_independent_no_cross_mix():
    """Option 0 wrong network; option 1 matches policy — pass with matching [1] only."""
    req_bad = PaymentRequirements(
        scheme="exact",
        network="eip155:1",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
    )
    req_ok = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req_bad, req_ok], error="test")
    )
    policy = BuyerPolicy(allowed_networks=frozenset({"eip155:84532"}))
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict == "pass"
    assert out.matching_accept_indexes == [1]


def test_amount_integer_string_no_float():
    """Reject non-decimal amount strings at option level (verdict fail or inconclusive)."""
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1e6",
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(max_amount_atomic=10**12)
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert out.verdict != "pass"
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `pytest tests/test_policy_check_evaluate.py -v --tb=short`  
Expected: `ImportError` or `evaluate_policy` / models missing until Step 3.

- [ ] **Step 3: Implement minimal `evaluate_policy` + models**

```python
# app/policy_check.py (excerpt)
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel
from x402.http import decode_payment_required_header

MAX_HEADER_BYTES = 65536
MAX_DECODED_JSON_BYTES = 262144
MAX_ACCEPTS = 16


class BuyerPolicy(BaseModel):
    allowed_networks: frozenset[str] | None = None
    allowed_pay_to: frozenset[str] | None = None
    allowed_assets: frozenset[str] | None = None
    allowed_schemes: frozenset[str] | None = None
    max_amount_atomic: int | None = None
    max_timeout_seconds: int | None = None
    require_matching_resource: bool = False
    expected_http_method: str | None = None


class RequestDigest(BaseModel):
    canonical_url: str | None = None
    http_method: str | None = None
    body_sha256: str | None = None


Verdict = Literal["pass", "fail", "inconclusive"]


@dataclass
class OptionResult:
    index: int
    passed: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class PolicyCheckResult:
    verdict: Verdict
    option_results: list[OptionResult]
    matching_accept_indexes: list[int]
    analysis_input_digest: str
    top_reasons: list[dict[str, str]]


def _wire_size(pr: Any) -> int:
    dumped = (
        pr.model_dump_json(by_alias=True)
        if hasattr(pr, "model_dump_json")
        else json.dumps(pr)
    )
    return len(dumped.encode("utf-8"))


def evaluate_policy(
    *,
    payment_required_header: str,
    policy: BuyerPolicy,
    request_digest: RequestDigest | None,
) -> PolicyCheckResult:
    if len(payment_required_header) > MAX_HEADER_BYTES:
        return PolicyCheckResult(
            verdict="inconclusive",
            option_results=[],
            matching_accept_indexes=[],
            analysis_input_digest="",
            top_reasons=[{"code": "oversized_input"}],
        )
    try:
        pr = decode_payment_required_header(payment_required_header)
    except Exception:
        return PolicyCheckResult(
            verdict="inconclusive",
            option_results=[],
            matching_accept_indexes=[],
            analysis_input_digest="",
            top_reasons=[{"code": "decode_error"}],
        )
    if _wire_size(pr) > MAX_DECODED_JSON_BYTES:
        return PolicyCheckResult(
            verdict="inconclusive",
            option_results=[],
            matching_accept_indexes=[],
            analysis_input_digest="",
            top_reasons=[{"code": "oversized_decoded"}],
        )
    accepts = list(getattr(pr, "accepts", []) or [])
    if len(accepts) > MAX_ACCEPTS:
        return PolicyCheckResult(
            verdict="inconclusive",
            option_results=[],
            matching_accept_indexes=[],
            analysis_input_digest="",
            top_reasons=[{"code": "accepts_too_many"}],
        )
    option_results: list[OptionResult] = []
    matching: list[int] = []
    for i, acc in enumerate(accepts):
        reasons: list[str] = []
        scheme = str(getattr(acc, "scheme", "") or getattr(acc, "scheme_id", "") or "")
        if policy.allowed_schemes and scheme not in policy.allowed_schemes:
            reasons.append("scheme_not_allowed")
        net = str(getattr(acc, "network", "") or "")
        if policy.allowed_networks and net not in policy.allowed_networks:
            reasons.append("network_not_allowed")
        # amount: int-only string
        raw_amt = getattr(acc, "amount", None)
        if raw_amt is not None:
            s = str(raw_amt).strip()
            if not s.isdigit():
                reasons.append("amount_not_integer_string")
            else:
                amt = int(s)
                if policy.max_amount_atomic is not None and amt > policy.max_amount_atomic:
                    reasons.append("amount_above_max")
        passed = len(reasons) == 0
        option_results.append(OptionResult(index=i, passed=passed, reasons=reasons))
        if passed:
            matching.append(i)
    verdict: Verdict = "fail"
    if not accepts:
        verdict = "inconclusive"
    elif matching:
        verdict = "pass"
    digest = hashlib.sha256(
        json.dumps(
            {
                "hdr_len": len(payment_required_header),
                "policy": policy.model_dump(mode="json"),
                "request_digest": request_digest.model_dump(mode="json") if request_digest else None,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return PolicyCheckResult(
        verdict=verdict,
        option_results=option_results,
        matching_accept_indexes=matching,
        analysis_input_digest=digest,
        top_reasons=[],
    )
```

- [ ] **Step 4: Run tests — expect PASS** for decode/oversize; flesh matrix in Task 1b.

Run: `pytest tests/test_policy_check_evaluate.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/policy_check.py tests/test_policy_check_evaluate.py
git commit -m "feat(policy-check): add evaluate_policy core with bounded decode"
```

### Task 1b: Unit matrix (amounts, casing, multi-option, adversarial)

**Files:**
- Modify: `tests/test_policy_check_evaluate.py`

- [ ] **Step 1: Add parametrized cases**

| Case | Expected |
|------|----------|
| `max_amount_atomic` exceeded | option fail, not pass |
| EVM pay_to differs only by checksum | pass after normalize |
| Solana address differs by case | fail (no lowercasing) |
| `accepts` > 16 | inconclusive `accepts_too_many` |
| `require_matching_resource` True but URL mismatch | that option fails |
| `body_sha256` present | inconclusive `body_binding_not_verifiable_offline` at aggregate or option |
| garbage nested JSON in `extra` | no code execution; decode only |

```python
@pytest.mark.parametrize(
    "amount,policy_max,ok",
    [
        ("1000000", 999999, False),
        ("1000000", 1000000, True),
    ],
)
def test_amount_ceiling(amount, policy_max, ok):
    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount=amount,
    )
    header = encode_payment_required_header(
        PaymentRequired(x402_version=2, accepts=[req], error="test")
    )
    policy = BuyerPolicy(max_amount_atomic=policy_max)
    out = evaluate_policy(payment_required_header=header, policy=policy, request_digest=None)
    assert (1 in out.matching_accept_indexes) is ok
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_policy_check_evaluate.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/test_policy_check_evaluate.py app/policy_check.py
git commit -m "test(policy-check): matrix for amounts, casing, bounds, binding"
```

### Task 2: Seller challenge + verify/settle for this product only

**Files:**
- Modify: `app/policy_check.py`
- Modify: `app/config.py`

**Interfaces:**
- Produces: `build_payment_required_header() -> str`, and `async def verify_and_settle(payment_signature: str, payment_required: str) -> dict` **exactly** as `app/diligence_pack.py` lines 137–189 (delegating to `VerifyPaymentInput` + `app.x402_services._verify_and_settle_payment`).

- [ ] **Step 1: Read reference**

Read: `app/diligence_pack.py` `build_payment_required_header` (lines 137–177) and `verify_and_settle` (lines 180–189).

- [ ] **Step 2: Implement `build_payment_required_header`** using `challenge_cache.get_or_build(PRODUCT_ID, fp, _build)` like diligence, with `resource_url=f"{settings.public_base_url.rstrip('/')}/x402/policy-check"`, `discovery_method="POST"`, price `settings.policy_check_price`, `PRODUCT_ID` constant (e.g. `policy-check-analysis`), discovery input/output examples for OpenAPI.

- [ ] **Step 3: Implement `verify_and_settle`** as a thin `async def` forwarding to `_verify_and_settle_payment` like `diligence_pack.verify_and_settle`.

- [ ] **Step 4: Commit**

```bash
git add app/policy_check.py app/config.py
git commit -m "feat(policy-check): seller challenge and settle entrypoints"
```

(Optional later: replace test helper `_minimal_valid_header` with `build_payment_required_header()` from this module once seller config is stable in CI.)

### Task 3: HTTP route (402 → pay → deliver once)

**Files:**
- Create: `app/policy_check_routes.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `evaluate_policy`, `verify_and_settle`, `settings.policy_check_enabled`
- Pattern: mirror `app/diligence_routes.py` `_402_body`, validate body with Pydantic before returning 402 (validate-then-charge)

- [ ] **Step 1: Write failing HTTP tests**

```python
# tests/test_policy_check_http.py
import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_unpaid_returns_402():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/x402/policy-check", json={"payment_required_header": "x", "policy": {}})
    assert r.status_code == 402
    assert "PAYMENT-REQUIRED" in r.headers


@pytest.mark.asyncio
async def test_feature_flag_off_503(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "policy_check_enabled", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/x402/policy-check", json={"payment_required_header": "x", "policy": {}})
    assert r.status_code == 503
    assert r.json().get("error") == "feature_disabled"
```

- [ ] **Step 2: Run — FAIL**

Run: `pytest tests/test_policy_check_http.py -v`

- [ ] **Step 3: Implement router + include**

- [ ] **Step 4: Run — PASS**

Run: `pytest tests/test_policy_check_http.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/policy_check_routes.py app/main.py tests/test_policy_check_http.py
git commit -m "feat(policy-check): HTTP POST /x402/policy-check with 402 gate"
```

### Task 4: Idempotency and conflict (Redis + in-memory)

**Files:**
- Modify: `app/policy_check_routes.py` (or shared `app/policy_check_delivery.py` if cleaner)
- Modify: `tests/test_policy_check_http.py`

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_same_idempotency_key_same_body_same_response(monkeypatch):
    """Two paid POSTs with same key + body: duplicate delivery without second settle (mocked settle)."""
    from app import policy_check
    from app.config import settings

    async def _fake_settle(_sig: str, _pr: str) -> dict:
        return {"success": True, "transaction": "0x" + "0" * 64}

    monkeypatch.setattr(settings, "policy_check_enabled", True)
    monkeypatch.setattr(policy_check, "verify_and_settle", _fake_settle)
    hdr = _minimal_valid_header()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = {"payment_required_header": hdr, "policy": {}}
        headers = {
            "Idempotency-Key": "idem-pol-1",
            "PAYMENT-SIGNATURE": "mock-signature-blob",
        }
        r1 = await client.post("/x402/policy-check", json=body, headers=headers)
        r2 = await client.post("/x402/policy-check", json=body, headers=headers)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()


@pytest.mark.asyncio
async def test_same_key_different_body_409(monkeypatch):
    from app import policy_check
    from app.config import settings

    async def _fake_settle(_sig: str, _pr: str) -> dict:
        return {"success": True, "transaction": "0x" + "1" * 64}

    monkeypatch.setattr(settings, "policy_check_enabled", True)
    monkeypatch.setattr(policy_check, "verify_and_settle", _fake_settle)
    hdr = _minimal_valid_header()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h = {"Idempotency-Key": "idem-pol-2", "PAYMENT-SIGNATURE": "mock-signature-blob"}
        r1 = await client.post("/x402/policy-check", json={"payment_required_header": hdr, "policy": {}}, headers=h)
        r2 = await client.post(
            "/x402/policy-check",
            json={"payment_required_header": hdr, "policy": {"allowed_networks": ["eip155:8453"]}},
            headers=h,
        )
    assert r1.status_code == 200
    assert r2.status_code == 409


def _minimal_valid_header() -> str:
    from x402.http import encode_payment_required_header
    from x402.schemas import PaymentRequired, PaymentRequirements

    req = PaymentRequirements(
        scheme="exact",
        network="eip155:84532",
        pay_to="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        amount="1000",
    )
    return encode_payment_required_header(PaymentRequired(x402_version=2, accepts=[req], error="test"))
```

- [ ] **Step 2: Implement** storage keyed by `sha256(payer_identity + idempotency_key)` where payer identity is derived from settled payment record (same as diligence/mcp_store patterns), value = canonical result JSON + digest.

- [ ] **Step 3: Redis failure** — when strict mode and Redis down, expect 503 or 402 per `mcp_commerce_redis_strict` alignment (document choice in code comment).

- [ ] **Step 4: Commit**

```bash
git add app/ tests/test_policy_check_http.py
git commit -m "feat(policy-check): idempotency and conflict handling"
```

### Task 5: MCP tool `x402.policy_check`

**Files:**
- Modify: `app/mcp_server.py`
- Modify: `app/tools_registry.py`
- Create: `tests/test_policy_check_mcp.py`

- [ ] **Step 1: Test** unpaid returns `CallToolResult` `isError=True` with structured body (pattern from `build_payment_required_result` usage elsewhere).

- [ ] **Step 2: Register tool** with payment wrapper so **server** challenge is built inside wrapper; tool handler receives inspected header via args only for evaluation, not for auth.

- [ ] **Step 3: Commit**

```bash
git add app/mcp_server.py app/tools_registry.py tests/test_policy_check_mcp.py
git commit -m "feat(policy-check): MCP tool x402.policy_check"
```

### Task 6: A2A skill parity

**Files:**
- Modify: `app/a2a_rpc.py`
- Modify: `app/agent_surface.py` (skill metadata)
- Create: `tests/test_policy_check_a2a.py`

- [ ] **Step 1: Bind** `buyer-payment-policy-check` → same `execute` as HTTP body.

- [ ] **Step 2: Test** `tasks/send` or existing harness used in `tests/test_a2a_durable_tasks.py`.

- [ ] **Step 3: Commit**

```bash
git add app/a2a_rpc.py app/agent_surface.py tests/test_policy_check_a2a.py
git commit -m "feat(policy-check): A2A skill buyer-payment-policy-check"
```

### Task 7: Discovery + OpenAPI example

**Files:**
- Modify: `app/agent_surface.py` (`paid_resources` entry)
- Modify: `app/openapi_spec.py` (`output_examples`)

- [ ] **Step 1: Add** `/x402/policy-check` to paid resources with method POST and price string.

- [ ] **Step 2: Add** `DISCOVERY_OUTPUT_EXAMPLE` in `policy_check.py` and wire in `output_examples`.

- [ ] **Step 3: Guard test** — extend existing openapi allowlist test if present.

Run: `pytest tests/ -q -k openapi` (adjust to repo test name)

- [ ] **Step 4: Commit**

```bash
git add app/agent_surface.py app/openapi_spec.py app/policy_check.py tests/
git commit -m "docs(policy-check): discovery and OpenAPI example for policy-check"
```

### Task 8: Full regression and quality gates

- [ ] **Step 1: Run full suite**

Run:

```bash
ruff check app tests
pytest tests/ -q --tb=line
```

Expected: all pass.

- [ ] **Step 2: Document rollout**

Add to `README.md`:
- Enable `POLICY_CHECK_ENABLED=true` only for production fee collection.
- Client must obtain inspected `PAYMENT-REQUIRED` out-of-band (`x402.probe`); this product does not fetch URLs.
- Analysis receipt digest ≠ merchant settlement finality.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(policy-check): rollout and pricing caveats"
```

### Rollback

1. Revert the merge commit or set `POLICY_CHECK_ENABLED=false` and remove router include (single commit undo).
2. No database migrations in this plan — Redis keys TTL like other task stores.

### Verification commands (operator)

```bash
# Local
pytest tests/test_policy_check_evaluate.py tests/test_policy_check_http.py -v

# Live discovery (no payment)
curl -sS -o /dev/null -w "%{http_code}\n" "https://x402-mcp.onrender.com/health"
curl -sS "https://x402-mcp.onrender.com/openapi.json" | jq '.paths["/x402/policy-check"]'

# Unpaid probe (expect 402 after implementation)
curl -sS -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" \
  -d '{"payment_required_header":"dummy","policy":{}}' \
  -H "x-demand-ignore: 1" "https://x402-mcp.onrender.com/x402/policy-check"
```

---

## Plan self-review

1. **Spec coverage:** Offline evaluation §§1–6 → Tasks 1–1b; seller auth separation → Tasks 2–6 + Global Constraints; idempotency §8 → Task 4; MCP/HTTP/A2A §9 → Tasks 3,5,6; discovery §registry → Task 7; flags §10 → Global Constraints + Task 3.
2. **Placeholder scan:** No TBD/TODO strings; remaining numeric caps are named constants with explicit bytes/counts.
3. **Type consistency:** `BuyerPolicy` / `PolicyCheckResult` names reused across tasks; `verify_and_settle(payment_signature, payment_required)` matches `app/diligence_pack.py:180-189`.

**Execution handoff**

**Plan complete and saved to `docs/superpowers/plans/2026-11-06-x402-policy-check.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
