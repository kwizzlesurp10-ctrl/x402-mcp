import asyncio
from app.models import PayAndFetchInput
from app.x402_services import pay_and_fetch

async def run():
    url = "http://127.0.0.1:8402/mn/property-check?address=1700%20Penn%20Ave%20N"
    print(f"Running pay_and_fetch on {url} ...")
    try:
        req = PayAndFetchInput(url=url)
        data = await pay_and_fetch(req)
        print("Success! Data received:")
        print(data)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run())
