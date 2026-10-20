# Agent Instructions — CDP API Keys + Base Sepolia Funding

**Goal:** Obtain valid Coinbase Developer Platform (CDP) Secret API credentials for this project, fund the **buyer** wallet on Base Sepolia with testnet USDC + ETH, and leave secrets only in local `.env` (never commit, never paste full secrets into chat/logs).

**Repo:** `x402` workspace root (or `x402-mcp` mirror).  
**Config file:** `.env` (create from `.env.example` if missing).

---

## Fixed values for this mission

| Item | Value |
|------|--------|
| **CDP project / entity portal** | https://portal.cdp.coinbase.com/entity_f385858e-b78e-5802-a0b4-11c15c6c91c9?project=32073fab-b766-4079-82e4-632a64b67837 |
| **API Keys page (same account)** | https://portal.cdp.coinbase.com/api-keys/secret |
| **CDP Faucet** | https://portal.cdp.coinbase.com/products/faucet |
| **Network** | **Base Sepolia** only (testnet) |
| **Buyer address to fund** | `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9` |
| **Buyer private key location** | `.env` → `EVM_PRIVATE_KEY` (already generated; do not rotate unless broken) |
| **Seller receive address** | `.env` → `X402_PAY_TO_ADDRESS` (do **not** replace with buyer address unless operator says so) |

**Buyer key rule:** `EVM_PRIVATE_KEY` must be 64 hex chars (optional `0x` prefix). It is **not** a 42-char address.

**Sandbox vs faucet:**  
Payments Sandbox transfers (`/sandbox/.../transfers/...`) are **simulated** and do **not** fund Base Sepolia. Only the **Faucet** product (or real testnet transfers) funds on-chain balances used by `pay_and_fetch`.

---

## Preconditions

1. Operator is signed into Coinbase / CDP in the browser session you control (or can complete interactive login).
2. Working directory contains project `.env`.
3. Prefer headed browser for portal steps (Google/Coinbase often block headless login).
4. Do **not** print full `CDP_API_KEY_SECRET` or `EVM_PRIVATE_KEY` in transcripts; report only: set/unset, lengths, and public addresses.

---

## Phase A — Open the project and locate API keys

### Step A1 — Open the project entity page

1. Navigate to:  
   https://portal.cdp.coinbase.com/entity_f385858e-b78e-5802-a0b4-11c15c6c91c9?project=32073fab-b766-4079-82e4-632a64b67837
2. If redirected to sign-in, complete login with the operator’s Coinbase account.
3. Confirm the **project** in the UI matches or is selectable as project `32073fab-b766-4079-82e4-632a64b67837`.
4. Screenshot or note any project name shown (for the operator log only).

### Step A2 — Find existing Secret API keys

1. Go to: https://portal.cdp.coinbase.com/api-keys/secret  
   (or use portal nav: **API Keys** → **Secret API keys** / equivalent).
2. List existing keys. For each key, record only:
   - key name / label  
   - key **id** (UUID) if visible  
   - created date / last used if shown  
3. **Never** expect the secret to be re-displayed for an old key. If only the ID is known and the secret is lost → create a **new** key (Step A3).

### Step A3 — Create a Secret API key (if none usable)

1. On the Secret API keys page, choose **Create API key** / **New secret key**.
2. Prefer **Ed25519** / default CDP secret format if offered.
3. Scope / permissions: enable whatever is needed for **wallet / faucet / platform** usage for this project (if scopes are granular, include EVM + faucet-related access; if only “full secret key”, accept default).
4. Download or copy the JSON immediately. Typical shape:

```json
{
  "id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "privateKey": "base64-encoded-ed25519-secret=="
}
```

5. Save the download locally as e.g. `Downloads/cdp_api_key.json` (operator machine), **or** write values straight into `.env` in Phase B.
6. Confirm:
   - `id` is a UUID (~36 chars)  
   - `privateKey` is base64, typically **88** chars when properly padded (`==` at end is normal; avoid truncated or double-padded secrets)

### Step A4 — Confirm project binding

1. Return to the entity/project URL from A1 and verify the new key appears under that project/account if the UI lists keys per project.
2. If the portal shows a **Wallet secret** / **CDP_WALLET_SECRET** requirement for non-custodial wallets, note it; faucet requests to an **external** buyer address usually need only Secret API key ID + secret (no wallet secret). Do not invent a wallet secret.

---

## Phase B — Write credentials into `.env`

### Step B1 — Update CDP variables only

Edit project `.env` (never commit):

```env
CDP_API_KEY_ID=<id from JSON>
CDP_API_KEY_SECRET=<privateKey from JSON>
```

Rules:

- Strip accidental quotes/spaces.
- Use the exact `privateKey` string from the download (correct base64 padding).
- Do **not** change `EVM_PRIVATE_KEY` or `X402_PAY_TO_ADDRESS` in this phase unless they are clearly wrong (address-in-key-field, empty, etc.).

### Step B2 — Sanity-check without leaking secrets

Report only:

| Check | Pass criteria |
|-------|----------------|
| `CDP_API_KEY_ID` | set, length ≈ 36 |
| `CDP_API_KEY_SECRET` | set, length ≈ 88 (or valid PEM if EC format) |
| `EVM_PRIVATE_KEY` | set, length 64 or 66 (`0x` + 64) |
| Derived buyer address | equals `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9` |
| `X402_PAY_TO_ADDRESS` | set, 42-char `0x` address |

Optional API probe (if `cdp-sdk` available):

```text
GET https://api.cdp.coinbase.com/platform/v2/evm/accounts
```

- **200** → credentials work.  
- **401** → key wrong, revoked, or from wrong account/project → recreate key (A3) and rewrite `.env`.

Do not log Authorization headers or JWTs.

---

## Phase C — Fund buyer on Base Sepolia (CDP Faucet)

### Step C1 — Open faucet

1. Navigate to: https://portal.cdp.coinbase.com/products/faucet  
2. Stay signed into the same CDP account as Phase A.

### Step C2 — Claim **ETH** (gas)

1. **Network:** Base Sepolia  
2. **Token:** ETH  
3. **Address:** `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`  
4. Click **Claim** / **Request**.  
5. Wait for success UI; copy tx hash if shown.  
6. Explorer (optional): https://sepolia.basescan.org/address/0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9  

### Step C3 — Claim **USDC**

1. Same page: **Network** Base Sepolia  
2. **Token:** USDC  
3. **Address:** `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`  
4. Click **Claim**.  
5. Record tx hash if available.

### Step C4 — Rate limits / failures

| Symptom | Action |
|---------|--------|
| Claim limit / wait 24h | Note remaining time; try Circle faucet as backup (Step C5) |
| Wrong network selected | Re-claim with Base Sepolia only |
| Address typo | Re-enter exact buyer address above |
| Portal captcha / human check | Hand off to operator for interactive solve |

### Step C5 — Backup faucet (optional)

If CDP faucet is limited:

1. https://faucet.circle.com/  
2. Asset: USDC  
3. Network: Base Sepolia  
4. Address: `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`  
5. Complete captcha / claim.  
6. Still claim **ETH** from CDP or another Base Sepolia ETH faucet for gas.

### Step C6 — Verify on-chain (required)

Use Base Sepolia public RPC (example):

- RPC: `https://sepolia.base.org`  
- USDC contract: `0x036CbD53842c5426634e7929541eC2318f3dCF7e`  
- Address: `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`

**Pass criteria:**

- ETH balance **> 0**  
- USDC balance **> 0** (6 decimals; e.g. 1 USDC = `1000000` atomic)

Or run:

```bash
python -m app.doctor
```

Expect check **Testnet USDC funded** = pass when buyer key is set and balance > 0.

---

## Phase D — Optional programmatic faucet (after keys work)

Only if Phase B API probe returns **200** (not 401):

```python
# Pseudocode — use cdp-sdk
# address = 0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9
# network = "base-sepolia"
# await cdp.evm.request_faucet(address=..., network="base-sepolia", token="eth")
# await cdp.evm.request_faucet(address=..., network="base-sepolia", token="usdc")
```

If still **401**, stop automation and return to Phase A3 (new key) or complete Phase C in the portal UI.

---

## Phase E — Definition of done

All must be true:

1. [ ] `.env` has working `CDP_API_KEY_ID` + `CDP_API_KEY_SECRET` (probe ≠ 401), **or** operator accepts faucet-only (no CDP API) for now.  
2. [ ] `EVM_PRIVATE_KEY` derives to `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`.  
3. [ ] Buyer has Base Sepolia **ETH > 0** and **USDC > 0**.  
4. [ ] `X402_PAY_TO_ADDRESS` still set for seller revenue.  
5. [ ] No secrets committed to git; `.env` remains gitignored.  
6. [ ] Operator summary includes: project URL used, whether key was created vs reused, faucet tx hashes or balance numbers, doctor result.

---

## Agent behavior rules

1. **Browser:** Prefer headed Chrome/Edge for CDP portal; use existing Google Drive Playwright auth only for Drive, not for Coinbase login.  
2. **Secrets:** Write to `.env` only; never commit; never echo full secrets.  
3. **Scope:** Do not switch buyer funds to mainnet; do not move mainnet money.  
4. **Do not** treat Payments Sandbox transfer URLs as funding proof.  
5. **Do not** put the buyer private key into MCP manifests that get shared; env on the vault/treasurer instance only.  
6. On blockers (login, captcha, 2FA, faucet cooldown), stop and report exact step + screenshot path.

---

## Quick operator copy-paste

**Project (keys):**  
https://portal.cdp.coinbase.com/entity_f385858e-b78e-5802-a0b4-11c15c6c91c9?project=32073fab-b766-4079-82e4-632a64b67837  

**Secret API keys:**  
https://portal.cdp.coinbase.com/api-keys/secret  

**Faucet:**  
https://portal.cdp.coinbase.com/products/faucet  
→ Base Sepolia → ETH, then USDC → `0x828942Ea72c767AB944C1cE80264F465b6cB6Fd9`

**`.env` targets:**

```env
CDP_API_KEY_ID=...
CDP_API_KEY_SECRET=...
EVM_PRIVATE_KEY=...   # already set for buyer 0x828942Ea...
X402_PAY_TO_ADDRESS=...
X402_DEFAULT_NETWORK=eip155:84532
```

---

## JWT authentication (Coinbase pitfalls)

When calling CDP or Coinbase REST APIs, regenerate a JWT **per request** with correct URI parts:

| Component | Rule | CDP example |
|-----------|------|-------------|
| **HTTP method** | Uppercase; match the call | `GET`, `POST` |
| **Host** | Product-specific | `api.cdp.coinbase.com` (CDP platform) — **not** `api.coinbase.com` (App/Advanced Trade) |
| **Path** | Exact endpoint path | `/platform/v2/evm/accounts`, `/platform/v2/evm/faucet` |
| **URI claim** | `{METHOD} {host}{path}` | `GET api.cdp.coinbase.com/platform/v2/evm/accounts` |

**Common pitfalls**

1. **Dynamic parameters** — Method, host, and path must be set at runtime for the endpoint being queried. Reusing a JWT minted for another path fails auth.
2. **Token expiration** — Default **120 seconds**. Increase only if proxies add latency; always mint a fresh JWT for each call.
3. **Key format** — Import **id** (name) + **privateKey** with original formatting (PEM newlines or base64 Ed25519). On 401, debug **lengths/prefixes only**, never full secrets.
4. **Clock skew** — `nbf` / `exp` need NTP-synced clocks; large skew → rejections.
5. **Header** — Must include correct `alg` (`EdDSA` for Ed25519, `ES256` for EC) and `kid` (key id).
6. **Payload bloat** — Only essential claims (`sub`, `iss`, `nbf`, `exp`, `uri`/`uris`).

**Local verify (no secret printing)**

```bash
python scripts/verify_cdp_jwt.py
python scripts/verify_cdp_jwt.py --method POST --path /platform/v2/evm/faucet
```

Helper module: `app/cdp_jwt.py` (`RequestTarget`, `generate_cdp_jwt`, `key_debug_info`).

CDP JWT docs: https://docs.cdp.coinbase.com/get-started/authentication/jwt-authentication

---

## Related docs

- [SETUP.md](SETUP.md) — wallet + MCP install  
- [agent-ops.md](agent-ops.md) — free vs vault instances  
- [runbook.md](runbook.md) — live testnet flow  
- CDP Faucet quickstart: https://docs.cdp.coinbase.com/faucets/introduction/quickstart  
