@@ -0,0 +1,82 @@
+# Bounties
+
+This document is the **public spec and receipt book** for paid bounties on this repository.
+It is an add-only ledger: entries are appended, never edited or removed.
+
+## Settlement
+
+- **Network:** Base (`eip155:8453`)
+- **Asset:** USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
+- **payTo:** `0xAB745e5F576667037696e78ba7dA28E193E4423D`
+- **Receiver explorer:** <https://basescan.org/address/0xAB745e5F576667037696e78ba7dA28E193E4423D>
+
+## Protocol (non-negotiable)
+
+1. Public spec lives on a `bounty:` issue.
+2. Operator delivers a **new file only** on `master`.
+3. Counterparty sends USDC on Base to `payTo`.
+4. Operator pastes the BaseScan tx hash on the issue.
+5. Issue closes **only after** the hash is on the thread.
+
+Fund-first variant: step 3 before step 2. Same close rule.
+
+## Open Child Bounties
+
+| Amount | Deliverable                  | Status |
+| ------ | ---------------------------- | ------ |
+| $5     | `docs/TOOL_LEGIBILITY.md`    | open   |
+| $15    | `docs/BAZAAR_AUDIT.md`       | open   |
+| $25    | `docs/LIVE_LEDGER.md`        | open   |
+| $0.01  | live x402 verification call  | open   |
+
+Child work must be filed as separate issues; do not edit app code.
+
+## Receipts
+
+Append completed bounty receipts below in this format:
+
+```
+### <date> - <deliverable>
+- Issue: #<number>
+- File: `<path>`
+- Tx: <basescan tx url>
+- Amount: <USDC amount>
+- payTo: 0xAB745e5F576667037696e78ba7dA28E193E4423D
+```
+
+<!-- Add-only: append new receipts below this line -->
