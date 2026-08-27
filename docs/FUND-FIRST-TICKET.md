# Fund-First Settle Ticket

Machine cashier twin of `docs/BOUNTIES.md` (issue #493, pay before delivery).

## Rail

| Field | Value |
|---|---|
| Product id | `fund-first-ticket` |
| HTTP | `GET /pay/ticket` |
| Free control | `GET /pay/ticket/sample` |
| Scheme | x402 v2 `exact` |
| Network | `eip155:8453` when CDP creds / `revenue_network` say mainnet (`resolve_revenue_network()`) |
| Asset | USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| payTo | `X402_PAY_TO_ADDRESS` (live cold receive `0xAB745e5F576667037696e78ba7dA28E193E4423D`) |
| List price | `fund_first_ticket_price` in `app/config.py` (`$0.05`) |

Unsigned `GET /pay/ticket` → HTTP 402. `PAYMENT-REQUIRED` `accepts[0].payTo` must equal the configured receive address. Signed retry settles via the CDP facilitator; the handler runs only after `on_after_settle` with `success is True`. The JSON ticket is the product. No ArcGIS / diligence pack compute on this path.

`GET /pay/ticket/sample` is free. It never settles. It describes price, the `payTo` field name, network, and how to retry `/pay/ticket` with `PAYMENT-SIGNATURE`.

## Live buyer → BaseScan credit

1. Unpaid probe (no coin movement):

```bash
curl -sS -D - "https://x402-mcp.onrender.com/pay/ticket" -o /tmp/ticket-402.json
```

Expect `HTTP/1.1 402`. Decode `PAYMENT-REQUIRED` (base64 JSON). `accepts[0].payTo` = `0xAB745e5F576667037696e78ba7dA28E193E4423D`. `accepts[0].network` = `eip155:8453` on the public CDP deploy. `accepts[0].amount` = `50000` (atomic USDC for `$0.05`).

2. Sample (no coin movement):

```bash
curl -sS "https://x402-mcp.onrender.com/pay/ticket/sample"
```

Expect `200` JSON with `"sample": true`.

3. Paid retry is operator-only. Do not run `scripts/settle_once.py` or a wallet settle from CI or from an agent session. After an operator settle, Basescan credit is `https://basescan.org/tx/<hash>` to payTo. Ledger row `product_id=fund-first-ticket` is written only when the facilitator returns `success=true`.

## Demand join

402 challenges and revenue rows both key `fund-first-ticket`. `/demand` joins on that string. Unsigned 402s count unless `x-demand-ignore` or a payment header is present.

## Grant

Ticket `grant` is a one-use capability for `POST /tasks/us-rental-diligence` via header `X-FUND-FIRST-TICKET`. Pack compute stays on the diligence route. Invalid/used grant does not skip that route's own 402.
