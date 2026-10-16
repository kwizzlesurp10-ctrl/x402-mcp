# MCP-native x402 buyer transport

This server implements the [x402 MCP payment flow](https://docs.x402.org/guides/mcp-server-with-x402) for commerce settlement tools.

## Tools

| Tool | Unpaid call | Paid retry |
|------|-------------|------------|
| `commerce.activate_pro` | Returns `402`-shaped MCP tool error with `accepts[]` | Unlocks Pro tier |
| `commerce.purchase_credits` | Same | Adds tool credits |

Free tools, HTTP `402` storefront paths, MailRail gating, and `city.sample` are unchanged.

## Wire format

- **Request meta (buyer → server):** `_meta["x402/payment"]` — JSON `PaymentPayload` (v2).
- **Response meta (server → buyer):** `_meta["x402/payment-response"]` — facilitator settlement receipt on success.
- **Challenge body:** `CallToolResult.structuredContent` with `x402Version`, `accepts`, `error`, and `resource` (`mcp://tool/<name>`).

Payment terms are **server-authored** (same builders as `commerce.pro_requirements` / `commerce.credits_requirements`). Caller-supplied price, `payTo`, or alternate `PAYMENT-REQUIRED` blobs are not used for verify/settle.

Settlement is **idempotent** per payment payload fingerprint: facilitator `settle` runs once; replays return the cached receipt without a second charge.

## Verification (no spend)

```bash
pip install -r requirements.txt
pytest tests/test_mcp_x402_payment.py -q
```

With a running local API (`make api`), an unpaid MCP `tools/call` for `commerce.activate_pro` should return `isError: true` and `structuredContent.accepts[0].network` matching `REVENUE_NETWORK` (default Base Sepolia in dev; `eip155:8453` when CDP mainnet creds are set).
