# Wallet split, public URL, and Bazaar listing

## Wallet roles

| Role | Env / file | Purpose |
|------|------------|---------|
| **Hot buyer** | `EVM_PRIVATE_KEY` in `.env` | Only `pay_and_fetch` spends (testnet funded) |
| **Cold receive** | `X402_PAY_TO_ADDRESS` + `.keys/cold-receive.key` | Seller `payTo` — revenue lands here |

`.keys/` is gitignored. Import the cold key into a wallet you control; **never** put it in `EVM_PRIVATE_KEY`.

## Public base URL

```env
PUBLIC_BASE_URL=https://lands-technological-remaining-exhibit.trycloudflare.com
```

Tunnel (dev) — Cloudflare quick tunnel (preferred over localtunnel):

```bash
cloudflared tunnel --url http://127.0.0.1:8402
# then set PUBLIC_BASE_URL to the printed https://*.trycloudflare.com URL and restart uvicorn
```

Paid resource: `{PUBLIC_BASE_URL}/demo/paid`

Poll for CDP Bazaar listing:

```bash
python scripts/poll_bazaar_listing.py --timeout 900 --interval 30
```

## Bazaar (CDP discovery)

Listing is **not** a separate “register” API. CDP indexes your endpoint when:

1. Route returns **402** with `extensions.bazaar` (declared on `/demo/paid`)
2. Facilitator is **CDP**: `X402_FACILITATOR_URL=https://api.cdp.coinbase.com/platform/v2/x402`
3. `CDP_API_KEY_ID` / `CDP_API_KEY_SECRET` auth verify/settle
4. At least one **successful settle** completes (buyer → cold)
5. Catalog cache can lag **up to ~10 minutes**

Check merchant listing:

```bash
curl "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant?payTo=0x05e1720bB82F86B5bc7940a99FDC702E32256357"
curl "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?query=x402-seller-demo&network=eip155:84532"
```

## Buyer self-test against public URL

```bash
# free probe
curl -i "$PUBLIC_BASE_URL/demo/paid"

# paid fetch (uses hot EVM_PRIVATE_KEY)
# MCP tool pay_and_fetch or app.x402_services.pay_and_fetch
```

## Doctor notes

Doctor checks **buyer** USDC (from `EVM_PRIVATE_KEY`), not cold balance. Cold balance only grows when buyers pay you.
