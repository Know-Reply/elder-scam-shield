# Elder Scam Shield — Cloud Run production container
# Multi-agent scam protection for elderly Japanese users

FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr (important for Cloud Run logs)
ENV PYTHONUNBUFFERED=1

# Cloud Run injects PORT; default to 8080
ENV PORT=8080

# Placeholder — set via Cloud Run environment or Secret Manager
ENV GOOGLE_CLOUD_PROJECT=""

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8080

# Run with uvicorn — Cloud Run injects $PORT; shell form for env var expansion
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
