FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run_stdio.py .
COPY manifests ./manifests

ENV HOST=0.0.0.0

# Render injects PORT at runtime; fall back to 8402 for local Docker usage.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8402}
