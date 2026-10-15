FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    CACHE_DIR=/data/cache \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Mutable state (provider cache + published snapshot) lives here.
RUN mkdir -p /data/cache /data/published
VOLUME ["/data"]

EXPOSE 8000

# Railway injects PORT; fall back to 8000 locally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
