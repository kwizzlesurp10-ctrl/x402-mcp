# Buyer payment-policy check — runbook

## What it is

`evaluate_policy` in `app/policy_check.py` decodes a **caller-supplied** merchant `PAYMENT-REQUIRED` header with the pinned SDK (`decode_payment_required_header`) and compares each `accepts[]` option to an explicit buyer policy. It does **not** HTTP-fetch the merchant, does **not** verify the inspected purchase on-chain, and does **not** treat `request_digest` as a cryptographic binding to an HTTP body (see `body_sha256` → inconclusive).

Delivery surfaces:

- `POST /x402/policy-check` — unpaid `402` + seller challenge; paid after verify+settle of **this server's** fee.
- MCP `x402.policy_check` — same economics; `_meta['x402/payment']` on retry.
- A2A skill `buyer-payment-policy-check` — same challenge path via JSON-RPC.

The **analysis receipt** digests actor inputs (inspected header hash + policy + optional digest fields) and optional own-fee settlement metadata — it is **not** a merchant settlement receipt.

## Configuration (env)

| Variable | Default | Notes |
|----------|---------|--------|
| `POLICY_CHECK_ENABLED` | `false` | When false, HTTP returns **503** `feature_disabled`; MCP returns structured error; skill is omitted from bindings. |
| `POLICY_CHECK_PRICE` | `$0.01` | Seller analysis fee (USDC, via existing seller rails). Not a revenue claim. |
| `POLICY_CHECK_MAX_HEADER_BYTES` | `65536` | Raw base64/header cap. |
| `POLICY_CHECK_MAX_DECODED_BYTES` | `262144` | Post-decode wire size cap. |
| `POLICY_CHECK_MAX_ACCEPTS` | `16` | Max `accepts[]` length. |
| `POLICY_CHECK_IDEMPOTENCY_REDIS_STRICT` | `true` | With `REDIS_URL` set + Redis unreachable, idempotent requests fail closed (**503**). |
| `X402_PAY_TO_ADDRESS` | — | Required for any paid surface (seller misconfigured → **503**). |

## Rollout

1. Deploy with **`POLICY_CHECK_ENABLED=false`** (default).
2. Verify seller config: `GET /health` shows `wallet_configured` as expected for your environment.
3. Enable in staging: `POLICY_CHECK_ENABLED=true`.
4. Run unpaid probe: `curl -s -o /dev/null -w "%{http_code}\n" -H "x-demand-ignore: 1" https://<host>/x402/policy-check` → expect **402** (not 422).
5. Enable production only after operator sign-off.

## Rollback

Set `POLICY_CHECK_ENABLED=false` and redeploy. No migration: idempotency keys are best-effort TTL in Redis / process memory.

## Production validation gaps (explicit)

- **Live chain settlement** of the analysis fee is not exercised by CI; hermetic tests mock `verify_and_settle`.
- **Facilitator/CDP** behavior differences (mainnet vs testnet) are environment-specific — validate `PAYMENT-SIGNATURE` + `PAYMENT-RESPONSE` on your target network before relying on receipts.
- **Demand / conversion** for this SKU is unproven — treat pricing as configurable hypothesis, not validated economics.

## Verification commands (no spend in CI)

Run from repo root (Python 3.12):

```bash
python3 -m pytest tests/test_policy_check_evaluate.py tests/test_policy_check_http.py tests/test_policy_check_mcp.py tests/test_policy_check_a2a.py -v
ruff check app/policy_check.py app/policy_check_routes.py tests/test_policy_check_*.py
```

Hosted dry probes (no wallet; unpaid should be 402 when enabled):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "x-demand-ignore: 1" "https://x402-mcp.onrender.com/x402/policy-check"
```
