FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WHISPER_CACHE_DIR=/app/whisper_models
ENV PYTHONPATH=/app 

# Increase pip timeout and retries to ensure large dependencies like PyTorch
# download reliably even on slower networks without failing.
RUN pip install --default-timeout=1000 --retries 10 -r requirements.txt

COPY . .

CMD ["python", "-m", "app.main"]