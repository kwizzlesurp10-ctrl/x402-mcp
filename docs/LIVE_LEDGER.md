# LIVE_LEDGER — x402-mcp paid storefront

Public, add-only sales snapshot. Numbers are seeded from the repo's own `sale`
issues and the live `/stats` endpoint. Zeros and quiet weeks are included on
purpose. Nothing here is invented.

- Source of truth: `https://github.com/kwizzlesurp10-ctrl/x402-mcp` (issues labeled `sale`)
- Live counters: `https://x402-mcp.onrender.com/stats`
- Cashier: `https://x402-mcp.onrender.com/.well-known/funding.json`
- Canonical payTo: `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` (Base USDC)
- Generated: 2026-09-17

## 1. Gross USDC received by payTo

| Period | Sales events | Gross USDC | Unique paying wallets |
|---|---:|---:|---:|
| Trailing 7d (2026-09-10 → 2026-09-17) | 1 | **0.01** | 1 |
| Trailing 30d (2026-08-18 → 2026-09-17) | 18 | **1.75** | 8 |
| All time (2026-07-30 → 2026-09-17) | 30 | **3.40** | 10 |

All figures below are **gross to payTo**, not net. No fee or chargeback data is
published by the platform, so net is `unknown`.

### All-time paying wallets (10 unique)

`0x7e8198…`, `0xc533bf…`, `0xc22c17…`, `0x9138fe…`, `0xc59e74…`,
`0x644678…`, `0x54e163…`, `0x6777e1…`, `0x7ef12b…`, `0xc9c7b3…`

The dominant buyer is `0xc22c17fc…`, responsible for the two $1.50 prints
(issue #478, #501) and most $0.01 prints. One wallet (`0x7e81988b…`) paid the
first recorded sale on 2026-07-30.

### Closed / acknowledged sales

| Issue | Date | USDC | From |
|---|---|---:|---|
| #270 | 2026-07-30 | 0.01 | `0x7e81988b…` |
| #460 | 2026-08-11 | 0.01 | `0xc533bf52…` |
| #501 | 2026-08-26 | 1.50 | `0xc22c17fc…` |
| #526 | 2026-09-06 | 0.01 | `0x7ef12be6…` |

Closed sales total **1.53 USDC**. The remaining 16 open sale issues total
**1.87 USDC** and are real on-chain transfers that the repo has not yet
acknowledged; they are counted in gross above because the transfer happened.

## 2. Top paid endpoints (all time, from live `/stats`)

| Endpoint | Paid attempts | Settled |
|---|---:|---:|
| `/repair/json` | 925 | 2 |
| `/cron/nextrun` | 584 | 0 |
| `/yaml/tojson` | 572 | 0 |
| `/diff` | 564 | 0 |
| `/text/extract` | 562 | 0 |
| `/domain/whois` | 464 | 0 |
| `/email/validate` | 394 | 0 |
| `/github/repo-stats` | 392 | 0 |
| `/dns/lookup` | 417 | 0 |
| `/price/crypto` | 114 | 0 |

`/repair/json` is the only endpoint with a confirmed settlement (2 × $0.001).
Every other paid attempt is an unpaid 402 challenge or a paid request whose
receipt has not been posted to the repo.

## 3. Settlement failures

**None observed.** No disputed, refunded, or failed transaction is recorded in
the repo's sale issues or in the live counters. There is no public `failed`
channel, so "no evidence of failure" is reported, not "zero failures".

## 4. Known caveats

- `paid_attempts` is overstated for rows recorded before the `challenges`
  column existed: every 402 was counted as a paid attempt then. Use
  `settled_success` as the revenue signal.
- `settled_success == 2` and total settled gross == **0.002 USDC** on the live
  counters. The $3.40 gross above comes from on-chain transfers reported as
  `sale` issues, which is a *different* (broader) signal than the facilitator's
  `settled_success` counter. Both are reported; they are not the same metric.
- The Penniless Agent's own wallet (`0x3D98800c64C345950E1eAaa076D88C12d1BF5F37`)
  is a buyer on the `penniless-data-utilities` storefront, not the payTo above.
  The two should not be conflated.
- Revenue the Penniless Agent has actually received is separately tracked in
  `revenue-baseline.json` (0.101 USDC: 0.001 x402 + 0.10 BasedAgents). It is not
  part of this ledger, which covers the kwizzlesurp10-ctrl storefront only.

## 5. Unknown

- Per-client class, product mix, and refund rate.
- p99/p50 latency for paid calls.
- Whether any of the 16 open sale issues will be acknowledged and closed.
- Any revenue outside the Base USDC rail.