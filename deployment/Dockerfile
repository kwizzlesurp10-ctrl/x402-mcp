# x402-mcp server image.
#
# SELLER-ONLY storefront usage (Base Network Pulse):
#   docker run --env-file seller.env -p 8402:8402 <image>
# The seller path (publish, serve 402, settle) needs only
# X402_PAY_TO_ADDRESS + CDP creds — NEVER EVM_PRIVATE_KEY (buyer-only).
# See deployment/seller.env.example and docs/SELLER-STOREFRONT.md.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run_stdio.py .
COPY manifests ./manifests

ENV HOST=0.0.0.0
ENV PORT=8402

EXPOSE 8402

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8402"]