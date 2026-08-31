@@ -0,0 +1,48 @@
+---
+name: Paid Bounty
+about: Canonical protocol for USDC bounty settlement via GitHub
+title: "bounty: <short deliverable description>"
+labels: bounty
+assignees: ''
+---
+
+## Deliverable
+
+<!-- Describe the exact file to be added on master. Do not modify existing app code. -->
+
+- **File path:** `docs/<FILENAME>.md`
+- **Amount:** $<AMOUNT> USDC
+
+## Settlement
+
+- **Network:** Base (`eip155:8453`)
+- **Asset:** USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
+- **payTo:** `0xAB745e5F576667037696e78ba7dA28E193E4423D`
+- **Explorer:** <https://basescan.org/address/0xAB745e5F576667037696e78ba7dA28E193E4423D>
+
+## Sequence (non-negotiable)
+
+1. Public spec lives on this `bounty:` issue.
+2. Operator delivers a **new file only** on `master`.
+3. Counterparty sends USDC on Base to `payTo`.
+4. Operator pastes the BaseScan tx hash below.
+5. Issue closes **only after** the hash is on this thread.
+
+Fund-first variant: step 3 before step 2. Same close rule.
+
+## Tx Hash
+
+<!-- Paste the BaseScan transaction URL here after payment -->
+
+## Notes
+
+- Child work must be filed separately; do not edit app code.
+- Keep the parent index issue (#493) open; close this child when the tx hash is pasted.
+- See `docs/BOUNTIES.md` for the full protocol and receipt ledger.
