# Product focus: what to invest in, and what to leave alone

**Decided 2026-08-02, from `/demand` rather than from opinion.** Read this before
building anything new on a paid endpoint.

**Directory / marketing Visit URLs (do not use Mission Control SPA):**

| Role | URL |
|------|-----|
| Catalog | https://x402-mcp.onrender.com/us/cities |
| Paid example | https://x402-mcp.onrender.com/us/sea/property-check |
| Free sample | https://x402-mcp.onrender.com/us/sea/property-check/sample |

See [CITY-NETWORK.md](CITY-NETWORK.md).

## The measurement

`app/demand.py` counts 402 challenges served per resource against sales settled,
keyed to the revenue ledger's `product_id`. It exists precisely because "nobody
has ever seen this listing" and "agents priced it and walked away" look
identical from outside and imply opposite next moves. It had never been read.

Read on 2026-08-02:

| Resource | Challenges | Qualified | Sales | Conversion | Revenue |
|---|---:|---:|---:|---:|---:|
| Pulse composite | 5,133 | 1,840 | 3 | **0.02%** | $0.35 |
| `/base/tx-decision` | 4,780 | 1,783 | 3 | **0.06%** | $0.03 |
| `/mn/property-check` | 25 | 15 | 2 | **4.0%** | $0.02 |

`mn-property-check` converts **66-200x better** than the other two, on traffic
roughly 200x smaller.

## What that means

The two high-traffic products do not have a discovery problem. They have been
seen thousands of times and converted at ~0.03%. Read the raw user agents in
`/demand` and most of that traffic is `x402-census-probe`, `AgentReeve`,
`x402-liveness-directory` and friends — a good number self-labelled
*"no payment sent"* / *"never pays"*. So do not read "1,900 qualified views" as
1,900 buyers who declined. Read it as: **this traffic was never demand, and more
listings produce more of it.**

The shape difference is the likely cause, and it was predicted independently
from the product alone before these numbers were read:

- `/base/tx-decision` sells `max_fee = 2 x base_fee + tip` over a free RPC call.
  A capable agent developer inlines that in five lines for $0.
- `/base/finality-check` reads block tags a buyer can read themselves for free.
- The Pulse composite is a synthesis of the same public inputs.
- `/mn/property-check` resells something with a real access barrier: three City
  of Minneapolis ArcGIS datasets, joined, normalised, and kept current.

Every seller on these rails that actually earns is reselling a real cost basis
or a real access barrier. We have exactly one product with that shape.

## The decision

**Invest in `/mn/property-check`.** It is the only endpoint that converts and
the only one no catalog has ever indexed — because until 2026-08-02 it answered
a parameterless crawler probe with `422` instead of `402`, which is on
x402scan's published list of registration failures. That is now fixed, its
catalog description has been rewritten for buyers rather than engineers, and it
is registered on x402scan and submitted to the gold-402 directory.

**Stop investing in the Pulse composite and `/base/tx-decision`.** Specifically:

- No new features, tiers, or repositioning.
- No further re-index settles to refresh their catalog entries.
- No outreach or directory submissions that lead with them.
- They stay deployed and listed. They cost nothing to serve, they are already
  cataloged, and they hold the only external sales this project has made. This
  is a decision to stop *spending* on them, not to delete them.

**Not a conclusion about x402.** The rail works: payments settle, the catalog
indexes, strangers have paid. The conclusion is about what we chose to sell on
it.

## What would reverse this

- `/mn/property-check` gets cataloged and still converts near zero at >200
  challenges — then the problem is the market, not the product shape, and the
  honest move is to stop selling data products here entirely.
- Either de-prioritised endpoint reaches ~1% conversion on its own — then the
  read was wrong and it deserves attention again.
- A buyer asks for a feature on one of them and is willing to pay for it. Real
  demand beats this table.

## Method note

`/demand` was built on 2026-07-24 and first read on 2026-08-02. Nine days of
building happened in between, some of it on the endpoints this table says to
stop building. Instruments only help if someone reads them; check this table
before the next product decision, not after.

---

## 2026-08-03 checkpoint — the 4% was ours

The table above is wrong, and the error was self-inflicted.

`/demand` counted every settled revenue row as a sale. It never consulted
`is_operator_settle`, even though the classifier already existed inline in the
`/ledger/{name}` route and `payer` was already threaded into every row. So the
metric this whole document rests on counted us settling against our own listing
as customer demand.

Measured 2026-08-03, read-only:

| | Then (as published) | Now (external only) |
|---|---:|---:|
| `/mn/property-check` challenges | 25 | **386** (277 qualified) |
| `/mn/property-check` sales | 2 → then 5 | **0 external**, 3 operator, 2 unknown |
| `/mn/property-check` conversion | **4.0%** | **0%** |

The three sales dated 2026-08-02 are `is_operator_settle: true` from
`0x67ffc9…` — the settles run to get the resource catalogued. Two older rows
have no `payer` at all (they predate payer threading) and are counted as
*unknown*, never as external. **Confirmed external sales for
`/mn/property-check`: zero.**

Two independent sources agree. The CDP Bazaar's own quality block reports
`l30DaysUniquePayers: 1` for it. And `scripts/market_scan.py` (added
2026-08-03) reads the same telemetry across the whole catalog: 5 calls, 1
payer.

The one confirmed external sale in this entire project's ledger remains the
2026-07-30 `base-tx-decision` row — the product this document says to stop
investing in.

### The reversal clause is close, but not yet fired

"Cataloged and still converts near zero at >200 challenges" now reads: cataloged
(2026-08-02T13:48:38Z), 386 challenges, 0% external conversion. Two of the three
conditions are met. The third is time — the listing is roughly one day old, and
concluding from that would be the same mistake in the opposite direction.

**Decision date: 2026-08-24**, three weeks post-catalog. Written down now so it
is not renegotiated later:

- **≥1 confirmed external sale** (`is_operator_settle: false`) → the shape works,
  keep investing.
- **Zero external sales at >600 challenges** → the reversal clause fires. Stop
  selling data products on this rail and stop paying keepalive settles.

Until then: no features, no repositioning, no repricing. Price is demonstrably
not the binding constraint at n=0.

### 2026-08-04 — freeze lifted (operator unfreeze)

The 2026-08-24 calendar gate is **lifted early by operator decision**. Work on
`/mn/property-check` and other cost-basis / access-barrier products is allowed
again: features, repositioning, and (careful) repricing may proceed under the
usual invariants (402-before-422, fingerprint, settle-then-revenue, prices only
in `app/config.py`).

What is **not** reversed:

- **Pulse composite and `/base/tx-decision` stay demoted.** No new features,
  re-index settles, or lead outreach. Let Bazaar delist when idle (~2026-08-21).
- **External-only conversion remains the score.** Operator settles are not
  demand. Read `sales_external` / `conversion`, not challenge volume alone.
- **The reverse clause is still available as a kill switch**, not a freeze:
  if `/mn/property-check` stays at 0 external sales at high challenge volume,
  stop selling pure data products on this rail and skip keepalive settles. That
  is a product decision you make from `/demand`, not a calendar lock.

Next focus while unfrozen: invest in `/mn/property-check` and/or design the
next product with a real cost basis or access barrier. Do not re-open free-RPC
synthesis as a growth path.

### The delisting cliff is dated and mostly intended

The CDP Bazaar drops resources after ~30 days with no settled payment. From the
catalog's own `lastUpdated`:

- `/base/tx-decision` and the Pulse composite last settled **2026-07-22** →
  dropped around **2026-08-21**. This is the intended consequence of the "no
  further re-index settles" decision above. Let them go.
- `/mn/property-check` last settled **2026-08-02** → dropped around
  **2026-09-01**. Keepalive ($0.01 + gas) is an operator call: pay only if you
  still intend to sell the product and have checked `GET /wallet`. If reverse
  clause fires (0 external at high volume), do not pay it either.

Do **not** change `PINNED_PULSE_PRODUCT_ID` (`render.yaml:52-59`) as part of any
delisting. It is embedded in the purchase URL already in the catalog, and
changing it 404s every indexed buyer. Delisting is not a reason to touch it.

### Method note, second entry

The first method note said instruments only help if someone reads them. The
sequel: an instrument that is read but wrong is worse than one that is ignored,
because it manufactures confidence. `/demand` now splits `sales_external` /
`sales_operator` / `sales_unknown` and reports `conversion` on external payers
only, with `conversion_including_operator` retained so this correction stays
auditable. Before trusting any conversion number from this repo, check which of
the two you are reading.
