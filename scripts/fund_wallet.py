import asyncio
import os
import sys
from cdp import CdpClient
from dotenv import load_dotenv

async def main():
    # Force reload of .env
    load_dotenv(override=True)
    
    api_key = os.getenv("CDP_API_KEY_ID")
    api_secret = os.getenv("CDP_API_KEY_SECRET")
    
    if not api_key or not api_secret:
        print("Error: CDP_API_KEY_ID and CDP_API_KEY_SECRET must be set in .env")
        print("Please create an API key at https://portal.cdp.coinbase.com/api-keys/secret")
        sys.exit(1)

    print("Initializing CDP Client...")
    # CdpClient configures itself from CDP_API_KEY_ID and CDP_API_KEY_SECRET implicitly if CDP_API_KEY_NAME is not set, 
    # but the Python SDK expects CDP_API_KEY_NAME instead of ID in some versions.
    # Let's explicitly pass them to be safe if possible, or just let it read the env.
    os.environ["CDP_API_KEY_NAME"] = api_key
    os.environ["CDP_API_KEY_PRIVATE_KEY"] = api_secret
    
    try:
        from cdp.client import Cdp
        Cdp.configure(api_key, api_secret)
        cdp = CdpClient()
    except Exception as e:
        print(f"Failed to initialize CDP client: {e}")
        cdp = CdpClient() # Fallback to default init
        
    # Check if we already have an EVM_PRIVATE_KEY
    private_key = os.getenv("EVM_PRIVATE_KEY")
    address = None
    
    if private_key:
        print("Found existing EVM_PRIVATE_KEY in .env.")
        try:
            from eth_account import Account
            account = Account.from_key(private_key)
            address = account.address
            print(f"Resolved address: {address}")
        except Exception as e:
            print(f"Failed to parse EVM_PRIVATE_KEY: {e}")
            sys.exit(1)
    else:
        print("No EVM_PRIVATE_KEY found in .env. Let's create a new one.")
        from eth_account import Account
        import secrets
        priv = "0x" + secrets.token_hex(32)
        account = Account.from_key(priv)
        address = account.address
        
        # Save to .env
        with open(".env", "a") as f:
            f.write(f"\nEVM_PRIVATE_KEY=\"{priv}\"\n")
        print(f"Generated new wallet: {address}")
        print("Saved EVM_PRIVATE_KEY to .env")

    print(f"\nRequesting testnet funds for {address} on base-sepolia...")
    
    try:
        print("- Requesting ETH...")
        eth_hash = await cdp.evm.request_faucet(
            address=address,
            network="base-sepolia",
            token="eth"
        )
        print(f"  ETH transaction: https://sepolia.basescan.org/tx/{eth_hash}")
    except Exception as e:
        print(f"  ETH faucet error: {e}")
        
    try:
        print("- Requesting USDC...")
        usdc_hash = await cdp.evm.request_faucet(
            address=address,
            network="base-sepolia",
            token="usdc"
        )
        print(f"  USDC transaction: https://sepolia.basescan.org/tx/{usdc_hash}")
    except Exception as e:
        print(f"  USDC faucet error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
