# x402.policy_check — Design Specification

**Branch basis:** `origin/master` @ `adfefeac73ebdc6524a5375e1ace0adf0b99dc1f`  
**Status:** Approved for implementation planning — **this document is not executable code.**

## 1. Product summary

**Name:** `x402.policy_check` (MCP), mirrored as HTTP `POST /x402/policy-check` and A2A skill `buyer-payment-policy-check` (exact A2A skill id to align with `app/agent_surface.py` naming conventions at implementation time).

**Purpose:** Paid **offline** buyer payment-**policy consistency** inspector. The caller supplies a **PAYMENT-REQUIRED** header value (base64 wire as carried in HTTP `PAYMENT-REQUIRED`). The service decodes it with the **pinned Python x402 SDK** (`x402.http.decode_payment_required_header` — same family as `app/x402_services.py`, `app/mcp_x402_payment.py`, tests) and evaluates **each** entry in `accepts[]` **independently** against an explicit **buyer policy** object.

**Non-goals (hard):**

- No outbound HTTP(S) fetch of merchant URLs for this product (no probe, no SSRF surface). Callers use `x402.probe` or `/probe` separately if they need live 402 text.
- No wallet signing, settlement, or facilitator calls for the **inspected** merchant challenge.
- No assertion of merchant honesty, chain finality, or that goods will be delivered.
- No “pass” when a **required** policy check cannot be performed from decoded fields (→ `inconclusive`).

**Economics hypothesis:** Default **$0.01 USDC** service fee for **this** analysis (configurable). This fee is **independent** of the atomic amount in the **inspected** `accepts[]`. Unit economics are **not validated**; pricing is operator-configurable.

## 2. Registry and naming (verified on `adfefeac…`)

| Surface | Proposed name | Present on master? |
|--------|----------------|---------------------|
| MCP tool | `x402.policy_check` | **No** — `app/tools_registry.py` lists `x402.probe`, `x402.verify`, etc.; `policy_check` is absent. |
| HTTP | `POST /x402/policy-check` | **No** — new path; must be added to `app/openapi_spec.py` allowlists and `app/agent_surface.py` `paid_resources()` for discovery parity. |
| A2A | Skill id `buyer-payment-policy-check` (or equivalent) | **No** — new skill block in `agent_card()` and binding in `app/a2a_rpc.py` `_skill_bindings()`. |

## 3. Trust boundaries

1. **Caller-supplied PAYMENT-REQUIRED** is **untrusted data** until decoded. Decoding uses SDK only; no `eval`, no dynamic import of payload contents.
2. **Buyer policy JSON** is **caller intent**. The service does **not** authenticate organizational policy (no LDAP, no signed policy doc). Output is purely “does this decoded challenge match these rules?”
3. **Inspection result is not a settlement receipt** for the inspected merchant. A separate **analysis receipt** (see §7) may be issued for **this** service’s paid delivery only.
4. **`max_timeout_seconds`** on `PaymentRequirements` (SDK: `max_timeout_seconds`) is a **protocol field** describing payment validity window — **not** an absolute cryptographic “invoice expiry” proof. Spec language must not imply chain-level expiry attestation.

## 4. Inputs

### 4.1 `payment_required_header` (required)

- **Type:** string — the **exact** value of HTTP header `PAYMENT-REQUIRED` as the buyer would see it (base64-encoded JSON wire for x402 v2).
- **Parsing:** `decode_payment_required_header(payment_required_header)` only. Invalid / oversized wire → `verdict: inconclusive`, reason `decode_error` / `oversized_input` (see §6).

### 4.2 `policy` (required)

Typed structure (conceptual; exact Pydantic model in implementation plan). In HTTP/MCP JSON, sets may be encoded as **arrays of strings** and normalized to frozensets server-side.

| Field | Required | Semantics |
|-------|----------|-----------|
| `allowed_networks` | optional set | CAIP-2 strings; if non-empty, each accept must have `network` ∈ set or option fails. |
| `allowed_pay_to` | optional set | **Normalized** payee addresses (see §5.2). |
| `allowed_assets` | optional set | Normalized asset identifiers per chain rules; empty + EVM-only v1 → compare to `expected_usdc_asset(network)` from `app/commerce_payment.py` pattern. |
| `allowed_schemes` | optional set | e.g. `["exact"]`; if non-empty, scheme must match. |
| `max_amount_atomic` | optional | **Decimal integer string** or JSON integer: ceiling on `accepts[i].amount` in **atomic units** (same wire format as SDK). |
| `max_timeout_seconds` | optional | int; option fails if `accept.max_timeout_seconds` **>** policy max (policy is a ceiling on seller-offered window). |
| `require_matching_resource` | optional bool | If true: require `accepts[i]`-level or top-level `resource` from decoded model to match `request_digest` (see §4.3). If binding cannot be evaluated → **inconclusive**, not pass. |
| `expected_extra_sha256` | optional | If set: SHA-256 hex of canonical JSON of `extra` for that accept (sorted keys); else skip extra binding. |

**Do not** invent or require SDK-unsupported fields.

### 4.3 `request_digest` (optional)

Caller-supplied binding hints — **not** cryptographically verified unless future protocol exposes proof:

| Field | Purpose |
|-------|---------|
| `canonical_url` | Compared to `resource.url` from decoded `PaymentRequired` when `require_matching_resource` is true (string normalize: scheme/host lower, strip trailing slash on path except root). |
| `http_method` | Compared to policy’s `expected_http_method` if policy supplies it. |
| `body_sha256` | Optional hex; if present must be string; no server-side re-hash of body (offline tool). Mismatch policy TBD in implementation — default **inconclusive** with reason `body_binding_not_verifiable_offline`. |

### 4.4 Bounded parsing

- Max decoded `accepts` length: **e.g. 16** (config constant); excess → `inconclusive`, `accepts_too_many`.
- Max header string length: **e.g. 64 KiB** before base64 decode; after decode, max JSON size **e.g. 256 KiB** (align with existing challenge patterns if any).

## 5. Evaluation rules

### 5.1 Per-option evaluation (no mixing)

For each `accepts[i]`:

1. Evaluate **only** fields present on that `PaymentRequirements` instance.
2. Collect **pass/fail** reasons for **that index** in `option_results[i]`.
3. **Never** merge favorable fields across different indexes (e.g. network from accept 0 and pay_to from accept 1).

### 5.2 Address and asset normalization

- **EVM (e.g. `eip155:*`):** compare `pay_to` and token `asset` as **0x-prefixed lowercase** hex for **42-char** addresses. Reject malformed length/charset as option-fail or inconclusive (explicit reason).
- **Solana (`solana:*` or as SDK encodes):** **case-sensitive** string compare for addresses per ecosystem rules — document in implementation; do not apply EVM lowercasing to Solana.
- **Amount:** interpret `amount` as **non-negative integer string** in atomic units using **Python `int` from decimal string only** — no `float`, no USDC symbol shortcut for comparison.

### 5.3 Aggregate verdict semantics

Let `eligible` = set of indices where **all** required policy checks for that option **pass**.

| Condition | Verdict |
|-----------|---------|
| Decode fails | `inconclusive` |
| `accepts` empty | `inconclusive` |
| Policy requests a check that cannot be performed offline (e.g. binding needs unavailable proof) | `inconclusive` |
| `eligible` non-empty | `pass` |
| Else | `fail` |

**Selected option(s):** Report **`matching_accept_indexes`** = sorted(eligible). If `pass`, optionally report **`selected_eligible_index`** = smallest index (deterministic) for single-choice clients; full set remains authoritative.

### 5.4 `max_timeout_seconds` semantics

Policy compares integers only: “seller-offered timeout ≤ buyer max” when buyer sets `max_timeout_seconds`. Do **not** describe this as “payment still valid until wall time T” unless the SDK and facilitator contract expose that — they do not in this product scope.

## 6. Outputs

```json
{
  "verdict": "pass|fail|inconclusive",
  "policy_schema_version": 1,
  "accepts_evaluated": 2,
  "option_results": [
    { "index": 0, "passed": false, "reasons": ["amount_above_max"] },
    { "index": 1, "passed": true, "reasons": [] }
  ],
  "matching_accept_indexes": [1],
  "selected_eligible_index": 1,
  "decoded_summary": {
    "x402_version": 2,
    "resource": { "url": "…" }
  },
  "analysis_receipt": {
    "schema_version": 1,
    "digest_sha256": "…"
  },
  "note": "Policy consistency only; not settlement proof."
}
```

- **`decoded_summary`:** Redacted subset (no secrets); mirrors patterns elsewhere for discovery.
- **No** mock “chain” results in production code paths; tests may use fakeredis/fixtures only.

## 7. Analysis receipt (this service)

- **Scope:** Hash over canonical JSON of: normalized inputs (`payment_required_header` digest, policy canonical form, `request_digest`, `policy_schema_version`, evaluator version string), **not** merchant settlement.
- **Purpose:** Reproducible consistency stamp for **this** paid analysis — **not** `PAYMENT-RESPONSE` for the inspected resource.
- **Authentication:** Tied to **this** service’s x402 settlement (HTTP `PAYMENT-RESPONSE` / MCP payment meta) — same payer settlement record as other products; **never** use caller-supplied inspected header as proof of payment for **this** service (see `app/commerce_payment.py` “must never verify against caller-supplied” pattern).

## 8. Idempotency and duplicate charge

- **Idempotency key:** Optional header `Idempotency-Key` or JSON field `idempotency_key` (max 128 chars). **Same** payer identity + **same** canonical input digest + same key → return **same** analysis body and **no** second ledger charge.
- **Conflict:** Same idempotency key with **different** input digest → **409** HTTP / structured error MCP — do not charge.
- **Storage:** Redis-backed when `REDIS_URL` live (align with `mcp_settlement_store` / commerce strict patterns); in-memory dev fallback documented with “not for multi-worker production.”

## 9. Surfaces (behavioral parity)

| Surface | Unpaid | Paid |
|---------|--------|------|
| HTTP | `402` + `PAYMENT-REQUIRED` for **this** product | `200` + analysis JSON + `PAYMENT-RESPONSE` settlement receipt for **this** fee |
| MCP | `PaymentRequired` / `_meta` x402 pattern per `app/mcp_server.py` | Same evaluator; payment wrapper separate from inspected header |
| A2A | `input-required` + x402 metadata | Same evaluator after `verify_and_settle` for **this** skill only |

**Challenge binding:** Build seller requirements from **server** `build_seller_requirements` / challenge cache like `app/tx_decision.py` / `diligence_pack` — **never** trust `payment_required_header` from client for auth.

## 10. Feature flags and safe defaults

- **`POLICY_CHECK_ENABLED`** (env): default **`false`** in new deployments until operator explicitly enables production fee collection.
- Default network/price follow `settings.x402_default_network` and new `policy_check_price: str = "$0.01"` (hypothesis).
- Tests: mock facilitator / fakeredis only; no mainnet spend in CI.

## 11. Relationship to existing code (reference)

- Decode path: `x402.http.decode_payment_required_header` (see `tests/test_mn_compliance.py`, `app/x402_services.py`).
- Seller challenge trust model: `app/commerce_payment.py` (lines 3–7, `validate_commerce_requirements` at 80–117 on `adfefeac…`).
- Paid HTTP 402-before-validate: `app/diligence_routes.py`, `app/main.py` property-check patterns.
- OpenAPI allowlist: `app/openapi_spec.py` `PUBLIC_FREE_PATHS` / `paid_paths()`.

## 12. Self-review (gaps and resolutions)

| Check | Result |
|-------|--------|
| Spec coverage vs user ask | Offline-only confirmed (§1). No external fetch. Tool name `x402.policy_check` and path `/x402/policy-check` stated. |
| Multi-option mixing | §5.1 forbids cross-accept field mixing. |
| Amount / float | §5.2 integer-only. |
| EVM vs Solana | §5.2 split rules. |
| maxTimeoutSeconds meaning | §5.4 non-cryptographic framing. |
| Idempotency / receipt | §8, §7. |
| Caller policy not authenticated | §3.2. |
| Placeholders | Numeric caps (16/64KiB) are **explicit examples**; final constants in implementation with env overrides documented in plan. |

---

**Document control:** Changes after implementation must update `policy_schema_version` and evaluator version string together.
