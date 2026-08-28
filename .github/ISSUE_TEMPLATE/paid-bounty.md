---
name: Paid USDC bounty
about: Fund add-only work. Settlement is USDC on Base to the published payTo. Not an investment.
title: "bounty: $X USDC — <one-line deliverable>"
labels: []
---

## Settlement (required)

- Network: Base (`eip155:8453`)
- Asset: USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- payTo: `0x8A897D546c22d726b45Fa25F0EBB56207E63fF4e`
- Amount: $______ USDC (atomic = amount * 1e6)
- This is payment for a delivered artifact or a voluntary tip. Not a token, not equity, not a raise.

## Public spec

- New file path (add-only, do not rewrite existing files):
- Acceptance tests (checkbox list):
- Out of scope:

## Sequence

1. Funder comments `FUNDED` + BaseScan tx hash paying `payTo`.
2. Operator delivers the new file on `master` (add-only).
3. Operator comments `DELIVERED` + file URL.
4. Funder comments `ACCEPTED` or files a spec-gap note within 24h.
5. Operator pastes the same tx hash into this issue and closes.

Alternate (deliver-first): operator ships the file, funder pays, operator pastes hash, close.

## Close rule

Do not close without a BaseScan URL whose `to` is `payTo` and asset is Base USDC.
