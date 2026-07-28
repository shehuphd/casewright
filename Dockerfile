FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY src/ src/
COPY templates/ templates/
COPY data/ data/
COPY app.py .

# Writable dirs for workups and traces — no volume means these reset on redeploy.
# Mount an Azure Files share here if persistence is needed.
RUN mkdir -p logs outputs/workups

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# 1 worker: free tier has 0.25 vCPU; no point spinning more.
# 120s timeout: LLM analysis calls can run 30–60 s on longer cases.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120", "app:app"]
