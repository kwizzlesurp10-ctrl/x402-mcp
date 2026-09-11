# LIVE_LEDGER.md

Honest revenue numbers for the x402-mcp storefront payTo address (`0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e`). Seeded from public GitHub `sale` issues. No dashboard code was rewritten. Where logs are not public, values are marked `unknown`.

## Trailing Periods

| Period | Gross USDC to payTo | Unique Paying Wallets | Settlement Failures | Top Paid Endpoints |
|--------|---------------------|-----------------------|---------------------|--------------------|
| Trailing 7d  | $0.0600 | 2 | 0 | unknown |
| Trailing 30d | $3.3700 | 8 | 0 | unknown |
| All time     | $3.3900 | 9 | 0 | unknown |

## Top Paying Wallets (All Time)

| Wallet | Gross USDC |
|--------|------------|
| `0xc22c17fc…` | $3.2400 |
| `0xc59e74ed…` | $0.0500 |
| `0xc533bf52…` | $0.0300 |
| `0x644678ad…` | $0.0200 |
| `0x7ef12be6…` | $0.0100 |

## Notes

- Data sourced entirely from public `sale` issues (e.g., `0xc22c17fc…` prints on 2026-08-26).
- `/ledger` endpoint currently returns `{"detail":"Not Found"}`, so automated ledger logs are not publicly readable.
- Settlement failures are `0` in the public issue tracker; actual CDP facilitator reverts are not exposed in issues.
- Top paid endpoints are `unknown` because issue titles do not specify which resource was purchased.
