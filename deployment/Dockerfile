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