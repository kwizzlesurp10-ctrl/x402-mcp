# x402 ops checklist (restart / sell / bazaar)

## One-command stack

```bash
cd C:\Users\Keith\x402   # or /mnt/c/Users/Keith/x402
bash scripts/stack_up.sh          # backend + Cloudflare tunnel; rewrites PUBLIC_BASE_URL
# USE_TUNNEL=0 bash scripts/stack_up.sh   # local only
bash scripts/stack_down.sh
```

Dashboard (separate):

```bash
cd dashboard && VITE_API_TARGET=http://127.0.0.1:8402 pnpm dev -- --host 0.0.0.0 --port 5173
```

## Restart checklist

1. **One process on :8402** — avoid Windows + Linux double-bind (doctor shows wrong vault).
2. **`.env` hygiene**
   - `EVM_PRIVATE_KEY` = 66-char hex (`0x` + 64), **never** a 42-char address
   - `X402_PAY_TO_ADDRESS` = cold receive (≠ buyer preferred)
   - `X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402` for Bazaar
   - `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` present
3. **Start** `scripts/stack_up.sh` → note printed public URL
4. **Doctor** `curl -s localhost:8402/doctor | jq .ok` → `true`
5. **Probe seller** `curl -i $PUBLIC/demo/paid` → **402** + `payment-required`
6. **Buyer pay** `pay_and_fetch` against public `/demo/paid`
7. **Bazaar** `python scripts/poll_bazaar_listing.py` (catalog lag ~10m after first CDP settle)

## Wallet split

| Role | Config | Notes |
|------|--------|-------|
| Hot buyer | `EVM_PRIVATE_KEY` | Funded testnet USDC/ETH for spends |
| Cold receive | `X402_PAY_TO_ADDRESS` + `.keys/cold-receive.key` | Import to a wallet you control |

Doctor checks **buyer** balance, not cold.

## Useful URLs

| Path | Use |
|------|-----|
| `/health` | Liveness |
| `/doctor` | Wizard checks |
| `/ops/status` | Compact ops snapshot |
| `/demo/paid` | Seller 402 resource |
| `/demo/paid/info` | Free metadata + bazaar link |
| `/ledger/revenue` | Settled seller demo rows |
| `/wallet` | Public balances only |

Mission Control UI: http://localhost:5173/

## Bazaar

- No separate register API.
- Needs: public URL + CDP facilitator + `extensions.bazaar` + **successful settle**.
- Merchant:  
  `https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=<cold>`

## Ephemeral tunnels

`*.trycloudflare.com` URLs change when cloudflared restarts. After restart:

1. New URL printed by `stack_up.sh`
2. `.env` `PUBLIC_BASE_URL` updated automatically
3. `/demo/paid` also uses **request Host** so live tunnel host is preferred for resource URL
4. Re-settle once if you need the new host indexed in Bazaar

## Do not

- Put cold private key in `EVM_PRIVATE_KEY`
- Commit `.env` or `.keys/`
- Run two uvicorns on 8402
- Expect Payments Sandbox transfers to fund Sepolia USDC
