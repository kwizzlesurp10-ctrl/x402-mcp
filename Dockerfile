# Multi-stage: bake the Vercel Mission Control SPA into the public seller image
# so /dashboard on Render matches https://x402-mission-control.vercel.app layout.
# API calls use same-origin (empty VITE_API_BASE_URL) — no cross-host CORS needed.

FROM node:22-bookworm-slim AS dashboard
WORKDIR /src
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
COPY dashboard/package.json dashboard/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY dashboard/ .
# Same-origin against the FastAPI host that serves this bundle.
ENV VITE_API_BASE_URL=
RUN pnpm run build

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run_stdio.py .
COPY manifests ./manifests
# Fresh SPA build overwrites any committed static bundle.
COPY --from=dashboard /src/dist/ ./app/static/mission_control/

ENV HOST=0.0.0.0

# Render injects PORT at runtime; fall back to 8402 for local Docker usage.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8402}
