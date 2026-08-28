# Public USDC bounties (add-only)

Legal cashier for this repo: **payment for delivered documentation / audit artifacts**, or a voluntary tip. Not a security. Not a token sale.

## Settlement rail (canonical)

| Field | Value |
|---|---|
| Network | Base, CAIP-2 `eip155:8453` |
| Asset | USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| payTo | `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e` |
| Explorer | https://basescan.org/address/0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e |
| Machine cashier | existing x402 storefront (e.g. $0.01 property-check) |

GitHub Sponsors, Polar, and thanks.dev settle **fiat**. They do not credit `payTo`. If those are used, the operator may later sweep USD→USDC; that sweep is separate from this protocol.

## Protocol

```
public spec → operator delivers NEW file only → counterparty sends USDC to payTo → tx hash pasted on the issue → close
```

Add-only constraint: new files under `docs/`, `.github/`, or `ledger/`. No rewrites of `app/`, live facilitators, or existing READMEs as part of a bounty.

## Open bounties

Filed as GitHub issues with title prefix `bounty:`.

| $ USDC | Deliverable (new file) | Acceptance |
|---:|---|---|
| 5 | `docs/TOOL_LEGIBILITY.md` | 16 tools scored on outcome / when-to-use / cost / example / failure |
| 15 | `docs/BAZAAR_AUDIT.md` | every discoverable resource has input shape + example output + price < $0.10 note |
| 25 | `docs/LIVE_LEDGER.md` | trailing paid calls, unique paying wallets, settlement fails, p99 if known |
| 0.01 | verification call | unpaid 402 vs paid 200 on a live city endpoint; sale-watch issue appears |

## Close template (paste on the issue)

```
DELIVERED: <url to new file on master>
PAID: https://basescan.org/tx/<hash>
payTo confirmed: 0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e
```
