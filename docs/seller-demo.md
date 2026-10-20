# Step 2 — Seller demo (`/demo/paid`)

Paid resource on your own server so spend + **revenue** both show up on Base Sepolia.

## Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/demo/paid/info` | free | Metadata + self-test instructions |
| GET | `/demo/paid` | **402** without payment | Returns `PAYMENT-REQUIRED` (`payTo` = `X402_PAY_TO_ADDRESS`) |
| GET | `/demo/paid` | paid | With `PAYMENT-SIGNATURE` → verify + settle → JSON secret |

Resource URL (default): `http://localhost:8402/demo/paid`  
Price: `X402_DEFAULT_PRICE` (default `$0.01`)  
Network: `X402_DEFAULT_NETWORK` (default `eip155:84532`)

## Self-test (vault pays your seller address)

```bash
# 1) Free 402 probe
curl -i http://127.0.0.1:8402/demo/paid

# 2) Auto-pay + fetch (uses EVM_PRIVATE_KEY)
# via MCP tool pay_and_fetch, or:
python - <<'PY'
import asyncio, os
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); os.environ[k.strip()]=v.strip()
from app.config import settings
from app.models import PayAndFetchInput
from app import x402_services
settings.evm_private_key = os.environ['EVM_PRIVATE_KEY']
print(asyncio.run(x402_services.pay_and_fetch(
    PayAndFetchInput(url='http://127.0.0.1:8402/demo/paid', preferred_network='eip155:84532')
)))
PY

# 3) Revenue ledger
curl -s http://127.0.0.1:8402/ledger/revenue | head
```

## Mission Control

- **402 Inspector** → paste `http://127.0.0.1:8402/demo/paid`  
- **Ledger** → `/ledger/revenue` shows `seller_demo` rows after successful settles  

## Notes

- Prefer **split wallets**: hot `EVM_PRIVATE_KEY` (buyer) ≠ cold `X402_PAY_TO_ADDRESS` (seller).  
  See [wallet-split-and-bazaar.md](wallet-split-and-bazaar.md).  
- Set `PUBLIC_BASE_URL` when exposing beyond localhost (tunnel or deploy).  
- Bazaar indexing requires CDP facilitator + one successful settle (not x402.org alone).
